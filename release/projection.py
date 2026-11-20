from fractions import Fraction

from release.calibration import StationCalibration
from release.evidence import CalibrationEvidence, HalfPlane, canonical_planes, closed_vertices


def project_station_calibration(calibration: StationCalibration):
    drift_limits = [(c, bound) for a, b, c, bound in calibration.rows if not (a or b) and c]
    drift_lower = max(bound / c for c, bound in drift_limits if c < 0)
    drift_upper = min(bound / c for c, bound in drift_limits if c > 0)
    if drift_lower > drift_upper:
        return CalibrationEvidence(empty=True)

    direct = []
    drift_adjusted = []
    for a, b, c, bound in calibration.rows:
        if not (a or b):
            if not c and bound < 0:
                return CalibrationEvidence(empty=True)
            continue
        if not c:
            direct.append(HalfPlane(a, b, bound))
        else:
            endpoint = drift_lower if c > 0 else drift_upper
            drift_adjusted.append(HalfPlane(a, b, bound - c * endpoint))

    # The drift-adjusted worksheet carries independent ranges for the two coordinates.
    vertices = closed_vertices(drift_adjusted)
    if not vertices:
        return CalibrationEvidence(empty=True)
    p_values, q_values = zip(*vertices)
    zero, one = Fraction(0), Fraction(1)
    axes = (
        HalfPlane(one, zero, max(p_values)), HalfPlane(-one, zero, -min(p_values)),
        HalfPlane(zero, one, max(q_values)), HalfPlane(zero, -one, -min(q_values)),
    )
    planes = canonical_planes((*direct, *axes))
    if not closed_vertices(planes):
        return CalibrationEvidence(empty=True)
    return CalibrationEvidence(planes)
