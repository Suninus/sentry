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

# TODO: This could probably be a generic Series fairly easily.
# TODO: Double check all of this math, ... it's easy to get wrong.
class ResolutionHistory(List[Tuple[Timestamp, long]]):
    def this_week_sum(self):
        return sum(value for (timestamp, value) in self[-7:])

    def last_week_sum(self):
        return sum(value for (timestamp, value) in self[-14:-7])

    def month_average_week_sum(self):
        return sum(value for (timestamp, value) in self) / 4


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
