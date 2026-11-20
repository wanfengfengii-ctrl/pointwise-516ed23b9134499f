import json
from dataclasses import dataclass
from uuid import uuid4

from intake.batches import get_batch, require_name
from intake.measurements import NamedMeasurement, apply_measurement_correction, make_measurement
from intake.normalization import DriftBounds, normalize_drift
from intake.store import station_transaction


@dataclass(frozen=True)
class MeasureRevision:
    revision_id: str
    batch: str
    station: str
    parent_revision: str | None
    drift: DriftBounds
    measurements: tuple[NamedMeasurement, ...]


def get_revision(store, batch, station, revision_id=None):
    spec = get_batch(store, batch, station)
    connection = store.connection
    if revision_id is None:
        (revision_id,) = connection.execute(
            'SELECT current_revision FROM station_batches WHERE batch = ? AND station = ?',
            (spec.batch, spec.station),
        ).fetchone()
    else:
        require_name(revision_id, 'revision ID')
    row = connection.execute(
        '''SELECT batch, station, parent_revision, drift, measurements
           FROM measure_revisions WHERE revision_id = ?''', (revision_id,),
    ).fetchone()
    if row is None:
        raise LookupError('measurement revision not found')
    actual_batch, actual_station, parent_revision, drift, measurements = row
    if (actual_batch, actual_station) != (batch, station):
        raise ValueError('measurement revision belongs to a different batch or station')
    return MeasureRevision(
        revision_id, batch, station, parent_revision, DriftBounds.from_data(json.loads(drift)),
        tuple(map(NamedMeasurement.from_data, json.loads(measurements))),
    )


def record(store, batch, station, measurements, *, drift=None, parent_revision=None):
    if not isinstance(measurements, (tuple, list)) or not measurements:
        raise ValueError('at least one named measurement is required')
    with station_transaction(store) as connection:
        spec = get_batch(store, batch, station)
        revision_id = f'{station}:{uuid4().hex}'
        incoming = tuple(make_measurement(spec, raw, revision_id) for raw in measurements)
        if len({measurement.name for measurement in incoming}) != len(incoming):
            raise ValueError('duplicate measurement name')
        if parent_revision is None:
            snapshot = incoming
            drift_bounds = normalize_drift(drift, spec.scales_um[2])
        else:
            parent = get_revision(store, batch, station, parent_revision)
            snapshot = apply_measurement_correction(parent.measurements, incoming)
            drift_bounds = parent.drift if drift is None else normalize_drift(drift, spec.scales_um[2])
        connection.execute(
            '''INSERT INTO measure_revisions
               (revision_id, batch, station, parent_revision, drift, measurements)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (revision_id, batch, station, parent_revision, json.dumps(drift_bounds.as_data()),
             json.dumps([measurement.as_data() for measurement in snapshot], ensure_ascii=False)),
        )
        connection.execute(
            'UPDATE station_batches SET current_revision = ? WHERE batch = ? AND station = ?',
            (revision_id, batch, station),
        )
    return MeasureRevision(revision_id, batch, station, parent_revision, drift_bounds, snapshot)
