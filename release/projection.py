from fractions import Fraction

from release.calibration import StationCalibration
from release.evidence import CalibrationEvidence, HalfPlane, canonical_planes, closed_vertices


def eliminate_private(rows):
    """Project {a*p + b*q + c*t <= d} onto the (p, q) plane exactly.

    The station's private zero-drift coordinate ``t`` must not reach the center.
    Fourier-Motzkin elimination of ``t`` is exact for closed half-planes: every
    positive-``c`` upper bound is paired with every negative-``c`` lower bound,
    and ``c == 0`` rows pass through unchanged.  No endpoint is relaxed, so
    segments and isolated points survive.
    """
    positive = [(a, b, c, d) for a, b, c, d in rows if c > 0]
    negative = [(a, b, c, d) for a, b, c, d in rows if c < 0]
    planes = [HalfPlane(a, b, d) for a, b, c, d in rows if not c]
    for a1, b1, c1, d1 in positive:
        for a2, b2, c2, d2 in negative:
            planes.append(HalfPlane(
                -c2 * a1 + c1 * a2,
                -c2 * b1 + c1 * b2,
                -c2 * d1 + c1 * d2,
            ))
    return planes


def project_station_calibration(calibration: StationCalibration):
    planes = []
    for plane in eliminate_private(calibration.rows):
        if not (plane.a or plane.b):
            # Constant row: 0 <= bound.  A negative bound makes the relation empty;
            # a nonnegative one carries no (p, q) information.
            if plane.bound < 0:
                return CalibrationEvidence(empty=True)
            continue
        planes.append(plane)
    canonical = canonical_planes(planes)
    if not closed_vertices(canonical):
        return CalibrationEvidence(empty=True)
    return CalibrationEvidence(canonical)
