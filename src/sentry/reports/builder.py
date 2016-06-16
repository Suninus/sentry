import itertools
import operator
import random
from datetime import datetime, timedelta

from typing import (
    cast,
    Mapping,
    Optional,
    Tuple,
)

from django.db.models.query import (  # type: ignore
    Q,
    QuerySet,
)

from sentry.app import tsdb  # type: ignore
from sentry.models import (  # type: ignore
    Activity,
    Organization,
    GroupStatus,
    Project,
    User,
)
from sentry.reports.types import (
    Interval,
    IssueStatistics,
    IssueReference,
    IssueListSpecification,
    IssueListItem,
    IssueListScore,
    Report,
    ReportStatistics,
    ReportStatisticsItem,
    ResolutionHistory,
    ScoredIssueList,
    ScoredIssueListItem,
    Timestamp,
    UserStatistics,
)
from sentry.reports.utilities import (
    merge_mappings,
    merge_series,
)


def simple_score((issue, statistics)):  # type: (IssueListItem) -> IssueListScore
    return float(statistics.events)


issue_list_specifications = {
    'new': IssueListSpecification(
        "New Issues",
        lambda start, end: Q(
            first_seen__gte=start,
            first_seen__lt=end
        ),
        score=simple_score,
        limit=5,
    ),
    'reopened': IssueListSpecification(
        "Reintroduced Issues",
        lambda start, end: Q(
            status=GroupStatus.UNRESOLVED,
            resolved_at__gte=start,
            resolved_at__lt=end,
        ),  # TODO: Is this safe?
        score=simple_score,
        limit=5,
    ),
    'most-seen': IssueListSpecification(
        "Most Seen Issues",
        lambda start, end: Q(
            last_seen__gte=start,
            last_seen__lt=end,
        ),  # XXX: This might be very large, it might make sense to start sketching this?
        score=simple_score,
        limit=5,
    ),
}


def sort_and_truncate_issues(specification, issues):
    # type: (IssueListSpecification, List[ScoredIssueListItem]) -> List[ScoredIssueListItem]
    return sorted(
        issues,
        key=lambda (item, score): score,
        reverse=True,
    )[:specification.limit]


def merge_reports(target, other):
    # type: (Report, Report) -> Report
    assert target.interval == other.interval, 'report intervals must match'

    def merge_report_statistics_item(left, right):
        # type: (Optional[ReportStatisticsItem], Optional[ReportStatisticsItem]) -> Optional[ReportStatisticsItem]
        if left is None and right is None:
            return None
        elif left is None:
            return right
        elif right is None:
            return left
        else:
            return ReportStatisticsItem(
                left.resolved + right.resolved,
                left.total + right.total,
            )

    def merge_scored_issue_lists(specification, left, right):
        # type: (IssueListSpecification, ScoredIssueList, ScoredIssueList) -> ScoredIssueList
        return ScoredIssueList(
            left.count + right.count,
            sort_and_truncate_issues(specification, left.issues + right.issues),
        )

    return Report(
        target.interval,
        ReportStatistics(
            merge_series(
                merge_report_statistics_item,
                target.statistics.series,
                other.statistics.series,
            ),
            ResolutionHistory(),
        ),
        merge_mappings(
            merge_scored_issue_lists,
            target.issues,
            other.issues,
        ),
    )


def prepare_project_series(project, queryset, start, end, rollup):
    # type: (Project, QuerySet, datetime, datetime, int) -> List[Tuple[Timestamp, ReportStatisticsItem]]
    # Fetch the resolved issues.
    resolved_issue_ids = queryset.filter(
        status=GroupStatus.RESOLVED,
        resolved_at__gte=start,
        resolved_at__lt=end,
    ).values_list('id', flat=True)

    resolution, timestamps = tsdb.get_optimal_rollup_series(start, end, rollup)
    assert resolution == rollup, 'series resolution does not match requested rollup duration'

    # Fetch the series data for the number of times each resolved issue was seen.
    resolved_event_series = reduce(
        lambda left, right: merge_series(operator.add, left, right),
        tsdb.get_range(
            tsdb.models.group,
            resolved_issue_ids,
            start,
            end,
            rollup
        ).values(),  # type: List[List[Tuple[int, int]]]
        [(timestamp, 0) for timestamp in timestamps],
    )

    # Fetch the series data for the number of times any issue on the project was seen.
    total_event_series = tsdb.get_range(
        tsdb.models.project,
        (project.id,),
        start,
        end,
        rollup,
    ).get(project.id, [])  # type: List[Tuple[int, int]]

    return merge_series(
        ReportStatisticsItem,
        resolved_event_series,
        total_event_series,
    )


def prepare_project_issue_list(specification, queryset, start, end, rollup):
    # type: (IssueListSpecification, Project, datetime, datetime, int) -> ScoredIssueList
    # Fetch all of the groups IDs that meet this constraint.
    issue_id_list = queryset.filter(
        specification.filter_factory(start, end)
    ).values_list('id', flat=True)

    issue_events = tsdb.get_sums(
        tsdb.models.group,
        issue_id_list,
        start,
        end,
        rollup,
    )  # type: Mapping[int, int]

    issue_users = tsdb.get_distinct_counts_totals(
        tsdb.models.users_affected_by_group,
        issue_id_list,
        start,
        end,
        rollup,
    )  # type: Mapping[int, int]

    issue_list = []
    for issue_id in issue_id_list:
        item = IssueListItem(
            IssueReference(issue_id),
            IssueStatistics(
                issue_events.get(issue_id, 0),
                issue_users.get(issue_id, 0),
            ),
        )
        issue_list.append((
            item,
            specification.score(item),
        ))

    return ScoredIssueList(
        len(issue_id_list),
        sort_and_truncate_issues(
            specification,
            issue_list,
        ),
    )


# TODO: Drop the period argument and ake this only for weekly reports.
def prepare_project_report(project, end, period):
    # type: (Project, datetime, timedelta) -> Report
    queryset = project.group_set.exclude(status=GroupStatus.MUTED)

    start = end - period
    rollup = int(period.total_seconds() / 7)

    issue_lists = {}
    for key, specification in issue_list_specifications.items():
        issue_lists[specification] = prepare_project_issue_list(
            specification,
            queryset,
            start,
            end,
            rollup,
        )

    # TODO: Store this series data somewhere for later querying to build
    # history.
    series = prepare_project_series(project, queryset, start, end, rollup)

    # TODO: Load me from wherever the history data was stored above.
    # TODO: Need to assert this is 7 * 4 (or less.)
    history = ResolutionHistory()

    return Report(
        Interval(start, end),
        ReportStatistics(
            series,
            history,
        ),
        issue_lists,
    )


def prepare_user_statistics(organization, user, start, end, rollup):
    # type: (Organization, User, datetime, datetime, int) -> UserStatistics
    resolved_issue_ids = Activity.objects.filter(
        project__organization_id=organization.id,
        user_id=user.id,
        type__in=(
            Activity.SET_RESOLVED,
            Activity.SET_RESOLVED_IN_RELEASE,
        ),
        datetime__gte=start,
        datetime__lt=end,
        group__status=GroupStatus.RESOLVED,  # only count if the issue is still resolved
    ).values_list('group_id', flat=True)

    return UserStatistics(
        len(resolved_issue_ids),
        tsdb.get_distinct_counts_union(
            tsdb.models.users_affected_by_group,
            resolved_issue_ids,
            start,
            end,
            rollup,
        ),
    )
