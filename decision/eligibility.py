from fractions import Fraction

from decision.intervals import RationalInterval
from decision.joint_region import JointCalibration
from decision.policy import GearRule
from release.evidence import HalfPlane, closed_vertices


def guaranteed_readings(region: JointCalibration, rule: GearRule):
    if not region.vertices:
        return ()
    zero, one = Fraction(0), Fraction(1)
    least_allowed = rule.deduction - rule.residual_limit
    most_allowed = rule.deduction + rule.residual_limit
    acceptable = closed_vertices((
        *region.planes,
        HalfPlane(zero, one, most_allowed),
        HalfPlane(zero, -one, -least_allowed),
    ))
    if not acceptable:
        return ()
    return (RationalInterval(acceptable[0][0], acceptable[-1][0]),)
