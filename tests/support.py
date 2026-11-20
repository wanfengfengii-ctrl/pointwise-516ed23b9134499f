import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from exchange.admission import accept
from exchange.envelope import canonical_envelope_body, seal_piece
from intake.batches import BatchSpec, register_batch
from intake.revisions import record
from release.issue import freeze
from reports.publish import publish
from reports.shift import initialize_workspaces


SAMPLE = Path(__file__).resolve().parents[1] / 'samples' / 'handover.json'
DOMAIN = [['0', '1', True, True]]
BAND = {
    'evidence_domain': DOMAIN,
    'low': [['0', '1/4', True, True]],
    'high': [['3/4', '1', True, True]],
    'manual': [['1/4', '3/4', False, False]],
}
DIAGONAL = {
    'evidence_domain': DOMAIN,
    'low': [['0', '1/2', True, True]],
    'high': [['1/2', '1', True, True]],
    'manual': [],
}
EMPTY = {'evidence_domain': [], 'low': [], 'high': [], 'manual': []}


def constraint(a, b, c, bound, op='=', units=('normalized',) * 3):
    return {'coefficients': [a, b, c], 'bound': bound, 'op': op, 'units': units}


def measurement(name, *constraints, value='1/2', unit='normalized'):
    return {'name': name, 'value': value, 'unit': unit, 'constraints': list(constraints)}


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    data = dict(case_id=case_id, input=inputs, expected=expected, actual=actual,
                downstream_expected=downstream_expected, downstream_actual=downstream_actual,
                code_paths=code_paths, oracle=oracle)
    print('POINTWISE_SCENARIO ' + json.dumps(data, ensure_ascii=False, sort_keys=True), flush=True)


class ShiftCase(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory(prefix='hengpu-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.sample = json.loads(SAMPLE.read_text(encoding='utf-8'))
        self.batch = self.sample['batch']
        self.inputs = {item['role']: item for item in self.sample['stations']}
        self.specs = {
            role: BatchSpec(self.batch, item['station'], role, item['scales_um'])
            for role, item in self.inputs.items()
        }
        self.workspace = initialize_workspaces(self.root, self.specs.values())

    def center(self):
        return closing(self.workspace.open_center())

    def station(self, role):
        return self.workspace.open_station(role)

    def seed(self, role, measurements=None, *, drift=None, spec=None):
        item = self.inputs[role]
        spec = self.specs[role] if spec is None else spec
        with self.station(role) as store:
            register_batch(store, spec)
            return record(store, spec.batch, spec.station,
                          item['measurements'] if measurements is None else measurements,
                          drift=item['drift'] if drift is None else drift)

    def issue(self, revision):
        role = self.workspace.roster.role_for(revision.station)
        with self.station(role) as store:
            return freeze(store, revision.batch, revision.station, revision.revision_id)

    def admit(self, piece):
        body = canonical_envelope_body(seal_piece(piece))
        with self.center() as center:
            return accept(center, piece.batch, body)

    def admitted_revision(self, revision):
        piece, _ = self.issue(revision)
        return self.admit(piece)

    def pair(self, alpha_measurements=None, beta_measurements=None):
        return (self.admitted_revision(self.seed('alpha', alpha_measurements)),
                self.admitted_revision(self.seed('beta', beta_measurements)))

    def finish(self, first, second):
        with self.workspace.offline(), self.center() as center:
            self.assertFalse(self.workspace.station_directory.exists())
            return publish(center, self.batch, first.piece_id, second.piece_id, 'v1')

    def correct_beta(self, parent):
        with self.station('beta') as store:
            return record(store, self.batch, parent.station, self.sample['beta_correction'],
                          parent_revision=parent.revision_id)

    def counts(self, connection):
        reports, = connection.execute('SELECT COUNT(*) FROM signed_reports').fetchone()
        receipts, = connection.execute('SELECT COUNT(*) FROM publish_receipts').fetchone()
        return reports, receipts

    def issue_counts(self, store):
        issues, = store.connection.execute('SELECT COUNT(*) FROM station_issues').fetchone()
        receipts, = store.connection.execute('SELECT COUNT(*) FROM issue_receipts').fetchone()
        return issues, receipts

    def exchange_counts(self, center):
        pieces, = center.execute('SELECT COUNT(*) FROM center_pieces').fetchone()
        receipts, = center.execute('SELECT COUNT(*) FROM acceptance_receipts').fetchone()
        return pieces, receipts
