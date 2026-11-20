from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from intake.normalization import parse_rational


@dataclass(frozen=True, order=True)
class HalfPlane:
    a: Fraction
    b: Fraction
    bound: Fraction

    def contains(self, p, q):
        return self.a * p + self.b * q <= self.bound

    def normalized(self):
        divisor = abs(self.a or self.b or Fraction(1))
        return HalfPlane(self.a / divisor, self.b / divisor, self.bound / divisor)


UNIT_BOX = tuple(HalfPlane(*map(Fraction, row)) for row in (
    (1, 0, 1), (-1, 0, 0), (0, 1, 1), (0, -1, 0),
))


def canonical_planes(planes):
    return tuple(sorted({plane.normalized() for plane in planes}.difference(UNIT_BOX)))


def closed_vertices(planes):
    # The implicit closed box makes every nonempty feasible set bounded.
    # This also finds vertices of segments and singleton sets.
    constraints = (*UNIT_BOX, *planes)
    vertices = set()
    for left, right in combinations(constraints, 2):
        determinant = left.a * right.b - right.a * left.b
        if not determinant:
            continue
        p = (left.bound * right.b - right.bound * left.b) / determinant
        q = (left.a * right.bound - right.a * left.bound) / determinant
        if all(plane.contains(p, q) for plane in constraints):
            vertices.add((p, q))
    return tuple(sorted(vertices))


@dataclass(frozen=True)
class CalibrationEvidence:
    planes: tuple[HalfPlane, ...] = ()
    empty: bool = False

    def contains(self, p, q):
        p, q = parse_rational(p), parse_rational(q)
        return not self.empty and 0 <= p <= 1 and 0 <= q <= 1 and all(
            plane.contains(p, q) for plane in self.planes
        )


@dataclass(frozen=True)
class StationPiece:
    issue_id: str
    batch: str
    station: str
    role: str
    revision_id: str
    evidence: CalibrationEvidence


def encode_evidence(evidence):
    return {
        'empty': evidence.empty,
        'planes': [[str(plane.a), str(plane.b), str(plane.bound)]
                   for plane in canonical_planes(evidence.planes)],
    }


def decode_evidence(data):
    if not isinstance(data, dict) or data.keys() != {'empty', 'planes'}:
        raise ValueError('invalid evidence fields')
    empty, records = data['empty'], data['planes']
    if type(empty) is not bool or not isinstance(records, list) or (empty and records):
        raise ValueError('invalid explicit evidence domain')
    planes = []
    for row in records:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('invalid half-plane shape')
        plane = HalfPlane(*map(parse_rational, row))
        if not (plane.a or plane.b):
            raise ValueError('evidence half-plane requires a coordinate coefficient')
        planes.append(plane)
    result = canonical_planes(planes)
    if not empty and not closed_vertices(result):
        raise ValueError('empty evidence requires explicit empty form')
    return CalibrationEvidence(result, empty)
