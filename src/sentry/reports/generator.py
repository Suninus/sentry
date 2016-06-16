import itertools
from datetime import datetime, timedelta
from random import Random

from django.contrib.webdesign.lorem_ipsum import WORDS  # type: ignore
from django.utils import timezone  # type: ignore
from typing import Tuple, List, Mapping, MutableMapping, Generator

from sentry.app import tsdb  # type: ignore
from sentry.constants import LOG_LEVELS  # type: ignore
from sentry.models import (  # type: ignore
    Group,
    GroupStatus,
    Organization,
    Team,
    Project
)
from sentry.reports.builder import (
    issue_list_specifications,
    sort_and_truncate_issues,
)
from sentry.reports.types import (
    Interval,
    IssueListItem,
    IssueStatistics,
    IssueReference,
    IssueListSpecification,
    ResolutionHistory,
    Report,
    ReportStatistics,
    ReportStatisticsItem,
    ScoredIssueList,
    ScoredIssueListItem,
    Timestamp,
    UserStatistics,
)


def make_message(random):  # type: (Random) -> str
    return ' '.join(random.sample(WORDS, (int(random.weibullvariate(8, 4)))))

def make_culprit(random):  # type: (Random) -> str
    return '{module} in {function}'.format(
        module='.'.join(''.join(random.sample(WORDS, random.randint(1, int(random.paretovariate(2.2))))) for word in xrange(1, 4)),
        function=random.choice(WORDS)
    )


def truncate_to_day(datetime):
    # type: (datetime) -> datetime
    return datetime.replace(hour=0, minute=0, second=0, microsecond=0)


def generate_report(organization, random, days=7):
    # type: (Organization, Random, int) -> Tuple[Report, UserStatistics, Mapping[IssueReference, Group]]

    interval = timedelta(hours=24)
    end = truncate_to_day(timezone.now())
    start = end - (interval * days)

    resolution, timestamps = tsdb.get_optimal_rollup_series(
        start,
        end,
        int(interval.total_seconds())
    )  # type: Tuple[int, List[Timestamp]]
    assert resolution == int(interval.total_seconds())

    team = Team(
        id=1,
        slug='example',
        name='Example Team',
        organization=organization,
    )

    project = Project(
        id=1,
        slug='example',
        name='Example Project',
        team=team,
        organization=organization,
    )

    groups = {}  # type: MutableMapping[IssueReference, Group]

    def make_issue_reference_generator():
        # type: () -> Generator[IssueReference, None, None]
        for i in itertools.count(1):
            reference = IssueReference(i)
            groups[reference] = Group(
                id=i,
                project=project,
                message=make_message(random),
                culprit=make_culprit(random),
                level=random.choice(LOG_LEVELS.keys()),
                status=random.choice((GroupStatus.RESOLVED, GroupStatus.UNRESOLVED)),
            )
            yield reference

    issue_reference_generator = make_issue_reference_generator()

    def make_scored_issue_list_item(specification):
        # type: (IssueListSpecification) -> ScoredIssueListItem
        users = random.randint(0, 2500) if random.random() < 0.8 else 0
        count = int(users * max(1, random.paretovariate(2.2)))
        if count < 1:
            count = random.randint(0, 2500)
        item = IssueListItem(
            next(issue_reference_generator),
            IssueStatistics(count, users),
        )
        return item, specification.score(item)

    def make_scored_issue_list(specification):
        # type: (IssueListSpecification) -> ScoredIssueList
        count = int(random.paretovariate(0.25))
        range = xrange(0, min(count, specification.limit))
        issues = [make_scored_issue_list_item(specification) for i in range]
        return ScoredIssueList(
            count,
            sort_and_truncate_issues(specification, issues),
        )

    issues = {}
    for key, specification in issue_list_specifications.items():
        issues[specification] = make_scored_issue_list(specification)

    def make_report_statistics_item():  # type: () -> ReportStatisticsItem
        total = random.randint(0, int(1e6))
        return ReportStatisticsItem(
            resolved=int(total * random.random()),
            total=total,
        )

    def make_history_series():  # type: () -> ResolutionHistory
        rollup = 60 * 60 * 24
        resolution, timestamps = tsdb.get_optimal_rollup_series(
            end - timedelta(days=7 * 4),
            end,
            rollup,
        )
        assert resolution == rollup
        return ResolutionHistory(
            [(timestamp, random.randint(0, 250)) for timestamp in timestamps]
        )

    report = Report(
        Interval(start, end),
        statistics=ReportStatistics(
            series=[(
                timestamp,
                make_report_statistics_item(),
            ) for timestamp in timestamps],
            history=make_history_series(),
        ),
        issues=issues,
    )

    user_statistics = UserStatistics(
        resolved=int(random.paretovariate(0.6)),
        users=int(random.paretovariate(0.2)) if random.random() < 0.9 else 0,
    )

    return report, user_statistics, groups
