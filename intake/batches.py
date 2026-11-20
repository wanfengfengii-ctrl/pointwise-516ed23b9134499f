import json
from dataclasses import dataclass
from fractions import Fraction

from intake.normalization import parse_rational
from intake.store import station_transaction


ROLES = ('alpha', 'beta')


def require_name(value, label):
    if not isinstance(value, str) or not value or value.strip() != value or not value.isprintable():
        raise ValueError(f'invalid {label}')
    return value


@dataclass(frozen=True)
class BatchSpec:
    batch: str
    station: str
    role: str
    scales_um: tuple[Fraction, Fraction, Fraction]

    def __post_init__(self):
        require_name(self.batch, 'batch')
        require_name(self.station, 'station')
        if self.role not in ROLES:
            raise ValueError('invalid station role')
        if not isinstance(self.scales_um, (list, tuple)) or len(self.scales_um) != 3:
            raise ValueError('three coordinate spans are required')
        scales = tuple(parse_rational(value) for value in self.scales_um)
        if min(scales) <= 0:
            raise ValueError('coordinate spans must be positive')
        object.__setattr__(self, 'scales_um', scales)


def get_batch(store, batch, station):
    require_name(batch, 'batch')
    require_name(station, 'station')
    row = store.connection.execute(
        'SELECT role, scales FROM station_batches WHERE batch = ? AND station = ?',
        (batch, station),
    ).fetchone()
    if row is None:
        raise LookupError('station batch not registered')
    role, scales = row
    return BatchSpec(batch, station, role, json.loads(scales))


def register_batch(store, spec):
    if not isinstance(spec, BatchSpec):
        raise ValueError('BatchSpec required')
    with station_transaction(store) as connection:
        connection.execute(
            '''INSERT INTO station_batches(batch, station, role, scales) VALUES (?, ?, ?, ?)
               ON CONFLICT(batch, station) DO NOTHING''',
            (spec.batch, spec.station, spec.role, json.dumps(tuple(map(str, spec.scales_um)))),
        )
        if get_batch(store, spec.batch, spec.station) != spec:
            raise ValueError('station batch registration conflicts with existing context')
    return spec
