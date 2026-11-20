import argparse
import json
import sqlite3
import sys
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.admission import accept
from exchange.catalog import initialize_exchange_catalog
from exchange.envelope import canonical_envelope_body, seal_piece
from exchange.registry import BatchRoster, initialize_registry, register_roster
from intake.batches import ROLES, BatchSpec, register_batch
from intake.revisions import record
from intake.store import StationStore, initialize_station_store
from release.catalog import initialize_issue_catalog
from release.issue import freeze
from reports.export import export_report
from reports.publish import publish
from reports.retrieve import read
from reports.store import initialize_report_store


@dataclass(frozen=True)
class Workspace:
    root: Path
    roster: BatchRoster

    @property
    def station_directory(self):
        return self.root / 'stations'

    def open_station(self, role):
        if role not in ROLES:
            raise ValueError('unknown workspace station role')
        return StationStore(self.station_directory / f'{role}.sqlite3')

    def open_center(self):
        connection = sqlite3.connect(self.root / 'center.sqlite3')
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    @contextmanager
    def offline(self):
        original = self.station_directory
        offline = self.root / 'stations.offline'
        if offline.exists():
            raise FileExistsError(offline)
        original.rename(offline)
        try:
            yield
        finally:
            offline.rename(original)


def initialize_workspaces(root, specs):
    specs = tuple(specs)
    if len(specs) != 2 or not all(isinstance(spec, BatchSpec) for spec in specs):
        raise ValueError('workspace requires two station batch contexts')
    by_role = {spec.role: spec for spec in specs}
    if by_role.keys() != set(ROLES) or len({spec.batch for spec in specs}) != 1:
        raise ValueError('workspace requires two roles for the same batch')
    alpha, beta = (by_role[role] for role in ROLES)
    workspace = Workspace(Path(root), BatchRoster(alpha.batch, alpha.station, beta.station))
    workspace.station_directory.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        with workspace.open_station(spec.role) as station:
            initialize_station_store(station)
            initialize_issue_catalog(station)
            register_batch(station, spec)
    with closing(workspace.open_center()) as center:
        initialize_registry(center)
        initialize_exchange_catalog(center)
        initialize_report_store(center)
        register_roster(center, workspace.roster)
    return workspace


def _body_from_record(workspace, spec, measurements, *, drift=None, parent_revision=None):
    with workspace.open_station(spec.role) as station:
        revision = record(station, spec.batch, spec.station, measurements,
                          drift=drift, parent_revision=parent_revision)
        piece, _ = freeze(station, spec.batch, spec.station, revision.revision_id)
    return revision.revision_id, canonical_envelope_body(seal_piece(piece))


def _offline_publish(workspace, alpha_id, beta_id):
    with workspace.offline(), closing(workspace.open_center()) as center:
        return publish(center, workspace.roster.batch, alpha_id, beta_id, 'v1')


def run_shift(root, sample, *, include_correction=True):
    batch = sample['batch']
    items = sample['stations']
    specs = tuple(BatchSpec(batch, item['station'], item['role'], item['scales_um']) for item in items)
    workspace = initialize_workspaces(root, specs)
    accepted, revisions = {}, {}
    for spec, item in zip(specs, items, strict=True):
        revision_id, body = _body_from_record(workspace, spec, item['measurements'], drift=item['drift'])
        revisions[spec.role] = revision_id
        with closing(workspace.open_center()) as center:
            accepted[spec.role] = accept(center, batch, body).piece_id
    before = _offline_publish(workspace, accepted['alpha'], accepted['beta'])
    after = None
    if include_correction:
        beta = next(spec for spec in specs if spec.role == 'beta')
        _, body = _body_from_record(workspace, beta, sample['beta_correction'], parent_revision=revisions['beta'])
        with closing(workspace.open_center()) as center:
            corrected_id = accept(center, batch, body).piece_id
        after = _offline_publish(workspace, accepted['alpha'], corrected_id)
    with workspace.offline(), closing(workspace.open_center()) as center:
        original = read(center, before.report_id)
        result = {
            'before': json.loads(export_report(center, original.report_id)),
            'original_reclaimed': original == before,
        }
        if after is not None:
            result['after'] = json.loads(export_report(center, after.report_id))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run an isolated calibration handover')
    parser.add_argument('mode', choices=('demo', 'incident'))
    default_sample = Path(__file__).resolve().parents[1] / 'samples' / 'handover.json'
    parser.add_argument('--sample', type=Path, default=default_sample)
    args = parser.parse_args(argv)
    sample = json.loads(args.sample.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='hengpu-shift-') as root:
        result = run_shift(root, sample, include_correction=args.mode == 'demo')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.mode == 'incident' and result['before']['assessment'] != sample['expected_before']:
        print('GEAR_SELECTION_MISMATCH', file=sys.stderr)
        return 1
    if not result['original_reclaimed']:
        print('REPORT_SNAPSHOT_MISMATCH', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
