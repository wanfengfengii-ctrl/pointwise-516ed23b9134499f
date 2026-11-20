from fractions import Fraction

from decision.intervals import RationalInterval, subtract_intervals
from decision.joint_region import JointCalibration, supported_readings
from decision.policy import GearRule
from release.evidence import HalfPlane, closed_vertices


def _slice_max(region, reading):
    vertices = closed_vertices((
        *region.planes,
        HalfPlane(Fraction(1), Fraction(0), reading),
        HalfPlane(Fraction(-1), Fraction(0), -reading),
    ))
    if not vertices:
        return None
    return max(q for _, q in vertices)


def _slice_min(region, reading):
    vertices = closed_vertices((
        *region.planes,
        HalfPlane(Fraction(1), Fraction(0), reading),
        HalfPlane(Fraction(-1), Fraction(0), -reading),
    ))
    if not vertices:
        return None
    return min(q for _, q in vertices)


def _projection(region, extra):
    vertices = closed_vertices((*region.planes, extra))
    if not vertices:
        return None
    return min(p for p, _ in vertices), max(p for p, _ in vertices)


def _bad_above(region, threshold):
    """p where some q in the cross-section exceeds ``threshold``.

    ``q`` reaches its maximum over the convex region on a p-slice at a
    constrained vertex, so the largest q anywhere is attained at a region
    vertex.  If that maximum does not exceed the threshold the slice is safe
    for every p.  Otherwise the region met with ``q >= threshold`` projects to
    a closed interval [L, R]; because the slice maximum is a concave function
    of p, the strictly-violating set is (L, R), gaining an endpoint only where
    that endpoint's own slice maximum still strictly exceeds the threshold.
    This keeps exact-limit readings usable and makes ordinary gaps open,
    including flat slices that sit exactly on the limit.
    """
    if not region.vertices or max(q for _, q in region.vertices) <= threshold:
        return ()
    projected = _projection(region, HalfPlane(Fraction(0), Fraction(-1), -threshold))
    if projected is None:
        return ()
    left, right = projected
    if left == right:
        peak = _slice_max(region, left)
        return (RationalInterval(left, left),) if peak is not None and peak > threshold else ()
    return (RationalInterval(left, right, _slice_max(region, left) > threshold,
                             _slice_max(region, right) > threshold),)


def _bad_below(region, threshold):
    """p where some q in the cross-section falls below ``threshold``."""
    if not region.vertices or min(q for _, q in region.vertices) >= threshold:
        return ()
    projected = _projection(region, HalfPlane(Fraction(0), Fraction(1), threshold))
    if projected is None:
        return ()
    left, right = projected
    if left == right:
        floor = _slice_min(region, left)
        return (RationalInterval(left, left),) if floor is not None and floor < threshold else ()
    return (RationalInterval(left, right, _slice_min(region, left) < threshold,
                             _slice_min(region, right) < threshold),)


def guaranteed_readings(region: JointCalibration, rule: GearRule, domain=None):
    if domain is None:
        domain = supported_readings(region)
    if not domain:
        return ()
    least_allowed = rule.deduction - rule.residual_limit
    most_allowed = rule.deduction + rule.residual_limit
    return subtract_intervals(domain, (*_bad_above(region, most_allowed),
                                       *_bad_below(region, least_allowed)))
