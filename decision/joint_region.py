from dataclasses import dataclass
from fractions import Fraction

from decision.intervals import RationalInterval
from release.evidence import HalfPlane, canonical_planes, closed_vertices


@dataclass(frozen=True)
class JointCalibration:
    planes: tuple[HalfPlane, ...]
    vertices: tuple[tuple[Fraction, Fraction], ...]


def build_joint_region(alpha, beta):
    if alpha.empty or beta.empty:
        return JointCalibration((), ())
    planes = canonical_planes((*alpha.planes, *beta.planes))
    return JointCalibration(planes, closed_vertices(planes))


def supported_readings(region):
    if not region.vertices:
        return ()
    return (RationalInterval(region.vertices[0][0], region.vertices[-1][0]),)
