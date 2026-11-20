from dataclasses import dataclass
from fractions import Fraction

from intake.revisions import MeasureRevision


@dataclass(frozen=True)
class StationCalibration:
    # Each row is a*p + b*q + c*t <= bound.
    rows: tuple[tuple[Fraction, Fraction, Fraction, Fraction], ...]


def build_calibration(revision: MeasureRevision):
    zero, one = Fraction(0), Fraction(1)
    rows = [
        (one, zero, zero, one), (-one, zero, zero, zero),
        (zero, one, zero, one), (zero, -one, zero, zero),
        (zero, zero, one, revision.drift.upper), (zero, zero, -one, -revision.drift.lower),
    ]
    for measurement in revision.measurements:
        for constraint in measurement.constraints:
            row = (*constraint.coefficients, constraint.bound)
            rows.append(row)
            if constraint.op == '=':
                rows.append(tuple(-value for value in row))
    return StationCalibration(tuple(dict.fromkeys(rows)))
