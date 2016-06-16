import itertools

from typing import (
    cast,
    Any,
    Callable,
    Dict,
    Mapping,
    TypeVar,
    Tuple,
)

from sentry.reports.types import Timestamp


T = TypeVar('T')
V = TypeVar('V')


def merge_mappings(function, target, other):
    # type: (Callable[[Any, T, T], T], Mapping[Any, T], Mapping[Any, T]) -> Mapping[Any, T]
    assert set(target.keys()) == set(other.keys())  # TODO: Fill in?

    result = cast(Dict[Any, T], {})
    for key in target:
        result[key] = function(key, target[key], other[key])

    return result


def merge_series(function, target, other):
    # type: (Callable[[T, T], V], List[Tuple[Timestamp, T]], List[Tuple[Timestamp, T]]) -> List[Tuple[Timestamp, V]]
    missing = object()

    def merge_point(left, right):
        # type: (Tuple[Timestamp, T], Tuple[Timestamp, T]) -> Tuple[Timestamp, V]
        assert left[0] == right[0], 'timestamps must match'
        return (left[0], function(left[1], right[1]))

    return [merge_point(*items) for items in itertools.izip_longest(target, other)]
