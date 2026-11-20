from dataclasses import dataclass
from fractions import Fraction

from intake.normalization import parse_rational


@dataclass(frozen=True)
class GearRule:
    name: str
    deduction: Fraction
    residual_limit: Fraction

    def as_data(self):
        return {'name': self.name, 'deduction': str(self.deduction), 'residual_limit': str(self.residual_limit)}

    @classmethod
    def from_data(cls, data):
        return cls(data['name'], parse_rational(data['deduction']), parse_rational(data['residual_limit']))


@dataclass(frozen=True)
class GearPolicy:
    name: str
    low: GearRule
    high: GearRule

    def as_data(self):
        return {'name': self.name, 'low': self.low.as_data(), 'high': self.high.as_data()}

    @classmethod
    def from_data(cls, data):
        return cls(data['name'], GearRule.from_data(data['low']), GearRule.from_data(data['high']))


_V1 = GearPolicy('v1', GearRule('low', Fraction(0), Fraction(1, 2)), GearRule('high', Fraction(1), Fraction(1, 2)))


def resolve_policy(name):
    if name != _V1.name:
        raise ValueError('unknown gear policy')
    return _V1
