import re
from dataclasses import dataclass
from fractions import Fraction


_INTEGER_RATIO = re.compile(r'[+-]?[0-9]+/[+-]?[0-9]+')
_DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
_UNIT_UM = {
    'nm': Fraction(1, 1000),
    'um': Fraction(1),
    'μm': Fraction(1),
    'µm': Fraction(1),
    'mm': Fraction(1000),
}


def parse_rational(value):
    if isinstance(value, Fraction) or type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            if _INTEGER_RATIO.fullmatch(value):
                numerator, denominator = value.split('/')
                return Fraction(int(numerator), int(denominator))
            if _DECIMAL.fullmatch(value):
                return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError('invalid rational value') from error
    raise ValueError('invalid rational value')


def rational_text(value):
    parse_rational(value)
    return value if isinstance(value, str) else str(value)


def coordinate_factor(span_um, unit):
    if unit == 'normalized':
        return Fraction(1)
    if not isinstance(unit, str) or unit not in _UNIT_UM:
        raise ValueError('unknown coordinate unit')
    return span_um / _UNIT_UM[unit]


@dataclass(frozen=True)
class RawConstraint:
    coefficients: tuple[str, str, str]
    units: tuple[str, str, str]
    op: str
    bound: str

    @classmethod
    def from_input(cls, raw):
        if not isinstance(raw, dict) or raw.keys() != {'coefficients', 'units', 'op', 'bound'}:
            raise ValueError('invalid constraint fields')
        coefficients, units, op = raw['coefficients'], raw['units'], raw['op']
        if not isinstance(coefficients, (tuple, list)) or len(coefficients) != 3:
            raise ValueError('constraint requires three coefficients')
        if not isinstance(units, (tuple, list)) or len(units) != 3:
            raise ValueError('constraint requires three units')
        if op not in ('=', '<=', '>='):
            raise ValueError('constraint must be closed')
        for unit in units:
            coordinate_factor(Fraction(1), unit)
        return cls(tuple(map(rational_text, coefficients)), tuple(units), op, rational_text(raw['bound']))

    def as_data(self):
        return {'coefficients': self.coefficients, 'units': self.units, 'op': self.op, 'bound': self.bound}


@dataclass(frozen=True)
class NormalizedConstraint:
    coefficients: tuple[Fraction, Fraction, Fraction]
    op: str
    bound: Fraction

    def as_data(self):
        return {'coefficients': tuple(map(str, self.coefficients)), 'op': self.op, 'bound': str(self.bound)}

    @classmethod
    def from_data(cls, data):
        return cls(tuple(map(parse_rational, data['coefficients'])), data['op'], parse_rational(data['bound']))


def normalize_constraint(raw, scales_um):
    if not isinstance(raw, RawConstraint):
        raw = RawConstraint.from_input(raw)
    coefficients = tuple(
        parse_rational(value) * coordinate_factor(scale, unit)
        for value, scale, unit in zip(raw.coefficients, scales_um, raw.units, strict=True)
    )
    bound = parse_rational(raw.bound)
    op = raw.op
    if op == '>=':
        coefficients = tuple(-coefficient for coefficient in coefficients)
        bound = -bound
        op = '<='
    first = next((coefficient for coefficient in coefficients if coefficient), Fraction(1))
    divisor = first if op == '=' else abs(first)
    return NormalizedConstraint(tuple(coefficient / divisor for coefficient in coefficients), op, bound / divisor)


@dataclass(frozen=True)
class DriftBounds:
    lower: Fraction
    upper: Fraction
    raw_lower: str
    raw_upper: str
    unit: str

    def as_data(self):
        return {
            'lower': str(self.lower), 'upper': str(self.upper),
            'raw_lower': self.raw_lower, 'raw_upper': self.raw_upper, 'unit': self.unit,
        }

    @classmethod
    def from_data(cls, data):
        return cls(parse_rational(data['lower']), parse_rational(data['upper']),
                   data['raw_lower'], data['raw_upper'], data['unit'])


def normalize_drift(raw, span_um):
    if not isinstance(raw, dict) or raw.keys() != {'lower', 'upper', 'unit'}:
        raise ValueError('bounded drift with one declared unit is required')
    unit = raw['unit']
    scale = coordinate_factor(span_um, unit)
    raw_lower, raw_upper = rational_text(raw['lower']), rational_text(raw['upper'])
    lower, upper = parse_rational(raw_lower) / scale, parse_rational(raw_upper) / scale
    if lower > upper:
        raise ValueError('drift bounds are reversed')
    return DriftBounds(lower, upper, raw_lower, raw_upper, unit)
