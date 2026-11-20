import json

from exchange.envelope import canonical_envelope_body, seal_piece
from release.catalog import reclaim_issue
from release.issue import freeze
from tests.support import ShiftCase, constraint, measurement, scenario


class ReleaseTests(ShiftCase):
    def test_missing_revision_does_not_issue(self):
        revision = self.seed('alpha')
        with self.station('alpha') as store:
            with self.assertRaises(LookupError):
                freeze(store, self.batch, revision.station, 'missing')
            self.assertEqual(self.issue_counts(store), (0, 0))

    def test_issued_relation_and_receipt(self):
        revision = self.seed('alpha')
        piece, receipt = self.issue(revision)
        body = json.loads(canonical_envelope_body(seal_piece(piece)))
        self.assertEqual(set(body), {'version', 'batch', 'station', 'role', 'issue_id', 'revision_id', 'evidence'})
        self.assertEqual(set(body['evidence']), {'empty', 'planes'})
        self.assertNotIn(revision.measurements[0].name, json.dumps(body))
        self.assertEqual(body['revision_id'], revision.revision_id)
        self.assertEqual(receipt.issue_id, piece.issue_id)
        supported = [piece.evidence.contains(0, 0), piece.evidence.contains(0, '1/4'), piece.evidence.contains(0, 1)]
        self.assertEqual(supported, [True, True, False], 'STATION_RELATION_MISMATCH')
        with self.station('alpha') as store:
            reclaimed = reclaim_issue(store, piece.issue_id)
            self.assertEqual(reclaimed, (piece, receipt))
            self.assertEqual(self.issue_counts(store), (1, 1))
        scenario('check_missing_revision.exact_relation', {'p': '0', 'tested_q': ['0', '1/4', '1']},
                 [True, True, False], supported, True, reclaimed == (piece, receipt),
                 ['release/calibration.py', 'release/projection.py', 'release/catalog.py'],
                 '在 p=0 时共同约束 q−p=t 化为 0≤q≤1/4')

    def test_two_drift_limits_share_one_private_value(self):
        # t >= q and t <= p must hold together, even with independently wide drift bounds.
        revision = self.seed('alpha', [measurement('correlated', constraint(0, 1, -1, 0, '<='),
                                                  constraint(-1, 0, 1, 0, '<='))],
                             drift={'lower': '-1000', 'upper': '1000', 'unit': 'nm'})
        piece, _ = self.issue(revision)
        self.assertTrue(piece.evidence.contains('1/3', '1/3'))
        self.assertTrue(piece.evidence.contains('2/3', '1/3'))
        self.assertFalse(piece.evidence.contains('1/3', '2/3'))
        self.assertEqual(str(revision.drift.upper), '1')

    def test_infeasible_station_revision_has_explicit_empty_evidence(self):
        revision = self.seed('alpha', [measurement('impossible', constraint(0, 0, 1, 1))])
        piece, receipt = self.issue(revision)
        self.assertTrue(piece.evidence.empty)
        self.assertEqual(piece.evidence.planes, ())
        self.assertFalse(piece.evidence.contains(0, 0))
        with self.station('alpha') as store:
            self.assertEqual(reclaim_issue(store, piece.issue_id), (piece, receipt))
