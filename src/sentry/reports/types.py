from datetime import datetime
import operator

from typing import (
    Callable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Tuple,
)
from django.db.models.query import Q  # type: ignore


Timestamp = int

IssueListScore = float

IssueReference = NamedTuple('IssueReference', [
    ('id', long),
])

IssueStatistics = NamedTuple('IssueStatistics', [
    ('events', long),
    ('users', long),
])

IssueListItem = NamedTuple('IssueListItem', [
    ('reference', IssueReference),
    ('statistics', IssueStatistics),
])

ScoredIssueListItem = Tuple[
    IssueListItem,
    IssueListScore,
]

IssueListSpecification = NamedTuple('IssueListSpecification', [
    ('label', unicode),
    ('filter_factory', Callable[[datetime, datetime], Q]),
    ('score', Callable[[IssueListItem], IssueListScore]),
    ('limit', int),
])

ScoredIssueList = NamedTuple('ScoredIssueList', [
    ('count', long),
    ('issues', List[ScoredIssueListItem]),
])

ReportStatisticsItem = NamedTuple('ReportStatisticsItem', [
    ('resolved', long),
    ('total', long),
])

# TODO: This schema is sort of garbage, this should probably just be a list
# containing four weeks of data.
ResolutionHistory = NamedTuple('ResolutionHistory', [
    ('this_week', int),
    ('last_week', Optional[int]),
    ('month_average', Optional[int]),
])

BaseReportStatistics = NamedTuple('BaseReportStatistics', [
    ('series', List[
        Tuple[
            Timestamp,
            ReportStatisticsItem,
        ],
    ]),
    ('history', ResolutionHistory),
])

class ReportStatistics(BaseReportStatistics):
    # NOTE: Need to find a better way to represent multi-dimensional series so
    # that these hacks aren't necessary.
    def total_max(self):  # type: () -> long
        return max(item.total for (timestamp, item) in self.series)

    def resolved_sum(self):
        return sum(item.resolved for (timestamp, item) in self.series)

Interval = NamedTuple('Interval', [
    ('start', datetime),
    ('end', datetime),
])

Report = NamedTuple('Report', [
    ('interval', Interval),
    ('statistics', ReportStatistics),
    ('issues', Mapping[IssueListSpecification, ScoredIssueList]),  # TODO: This should be ordered.
])

UserStatistics = NamedTuple('UserStatistics', [
    ('resolved', long),
    ('users', long),
])
