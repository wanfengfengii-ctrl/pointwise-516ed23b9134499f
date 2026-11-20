from dataclasses import dataclass
from fractions import Fraction

from intake.normalization import parse_rational


@dataclass(frozen=True)
class RationalInterval:
    left: Fraction
    right: Fraction
    left_closed: bool = True
    right_closed: bool = True

    def __post_init__(self):
        object.__setattr__(self, 'left', parse_rational(self.left))
        object.__setattr__(self, 'right', parse_rational(self.right))
        if type(self.left_closed) is not bool or type(self.right_closed) is not bool:
            raise ValueError('interval endpoint flags must be boolean')
        if self.left > self.right or (self.left == self.right and not (self.left_closed and self.right_closed)):
            raise ValueError('interval is empty')

    def contains(self, point):
        return (self.left < point or (point == self.left and self.left_closed)) and (
            point < self.right or (point == self.right and self.right_closed)
        )


def normalize_intervals(intervals):
    arranged = sorted(intervals, key=lambda span: (span.left, not span.left_closed, span.right))
    result = []
    for span in arranged:
        if not result:
            result.append(span)
            continue
        previous = result[-1]
        touches = previous.right == span.left and (previous.right_closed or span.left_closed)
        if previous.right < span.left or (previous.right == span.left and not touches):
            result.append(span)
            continue
        if span.right > previous.right:
            result[-1] = RationalInterval(previous.left, span.right, previous.left_closed, span.right_closed)
        elif span.right == previous.right:
            result[-1] = RationalInterval(previous.left, previous.right, previous.left_closed,
                                          previous.right_closed or span.right_closed)
    return tuple(result)


def _nonempty_span(left, right, left_closed, right_closed):
    if left < right or (left == right and left_closed and right_closed):
        return RationalInterval(left, right, left_closed, right_closed)
    return None


def _subtract_one(span, cut):
    left, right = max(span.left, cut.left), min(span.right, cut.right)
    overlap = _nonempty_span(left, right, span.contains(left) and cut.contains(left),
                             span.contains(right) and cut.contains(right))
    if overlap is None:
        return (span,)
    before = _nonempty_span(span.left, left, span.left_closed, span.contains(left) and not overlap.left_closed)
    after = _nonempty_span(right, span.right, span.contains(right) and not overlap.right_closed, span.right_closed)
    return tuple(piece for piece in (before, after) if piece is not None)


def subtract_intervals(intervals, exclusions):
    remaining = normalize_intervals(intervals)
    for cut in normalize_intervals(exclusions):
        remaining = tuple(piece for span in remaining for piece in _subtract_one(span, cut))
    return remaining


def encode_intervals(intervals):
    return [[str(span.left), str(span.right), span.left_closed, span.right_closed] for span in intervals]


def decode_intervals(data):
    if not isinstance(data, list):
        raise ValueError('invalid interval list')
    intervals = []
    for row in data:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('invalid interval record')
        intervals.append(RationalInterval(*row))
    if tuple(intervals) != normalize_intervals(intervals):
        raise ValueError('interval list is not in canonical order')
    return tuple(intervals)
