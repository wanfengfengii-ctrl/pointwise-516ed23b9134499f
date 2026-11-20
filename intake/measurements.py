from dataclasses import dataclass
from fractions import Fraction

from intake.batches import require_name
from intake.normalization import (
    NormalizedConstraint, RawConstraint, coordinate_factor, normalize_constraint, parse_rational, rational_text,
)


@dataclass(frozen=True)
class NamedMeasurement:
    name: str
    value: str
    unit: str
    normalized_value: Fraction
    origin_revision: str
    raw_constraints: tuple[RawConstraint, ...]
    constraints: tuple[NormalizedConstraint, ...]

    def as_data(self):
        return {
            'name': self.name, 'value': self.value, 'unit': self.unit,
            'normalized_value': str(self.normalized_value), 'origin_revision': self.origin_revision,
            'raw_constraints': [row.as_data() for row in self.raw_constraints],
            'constraints': [row.as_data() for row in self.constraints],
        }

    @classmethod
    def from_data(cls, data):
        return cls(
            data['name'], data['value'], data['unit'], parse_rational(data['normalized_value']),
            data['origin_revision'], tuple(map(RawConstraint.from_input, data['raw_constraints'])),
            tuple(map(NormalizedConstraint.from_data, data['constraints'])),
        )


def make_measurement(spec, raw, origin_revision):
    if not isinstance(raw, dict) or raw.keys() != {'name', 'value', 'unit', 'constraints'}:
        raise ValueError('invalid measurement fields')
    name = require_name(raw['name'], 'measurement name')
    unit = raw['unit']
    value = rational_text(raw['value'])
    normalized_value = parse_rational(value) / coordinate_factor(spec.scales_um[1], unit)
    if not isinstance(raw['constraints'], (tuple, list)):
        raise ValueError('measurement constraints must be a sequence')
    original = tuple(map(RawConstraint.from_input, raw['constraints']))
    normalized = tuple(normalize_constraint(row, spec.scales_um) for row in original)
    return NamedMeasurement(name, value, unit, normalized_value, origin_revision, original, normalized)


def apply_measurement_correction(original, replacements):
    changes = {measurement.name: measurement for measurement in replacements}
    if len(changes) != len(replacements):
        raise ValueError('duplicate correction measurement name')
    names = {measurement.name for measurement in original}
    if not changes.keys() <= names:
        raise ValueError('correction names a measurement absent from its parent')
    return tuple(changes.get(measurement.name, measurement) for measurement in original)
