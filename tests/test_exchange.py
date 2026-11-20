import json
from dataclasses import replace

from exchange.admission import accept
from exchange.catalog import get_accepted_piece
from exchange.envelope import canonical_envelope_body, seal_piece
from exchange.registry import register_roster
from release.evidence import CalibrationEvidence
from reports.publish import publish
from tests.support import BAND, ShiftCase


class ExchangeTests(ShiftCase):
    def test_mixed_batches_cannot_publish(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        spec = replace(self.specs['beta'], batch='other-batch')
        with self.center() as center:
            register_roster(center, replace(self.workspace.roster, batch=spec.batch))
        beta_other = self.admitted_revision(self.seed('beta', spec=spec))
        with self.workspace.offline(), self.center() as center:
            with self.assertRaisesRegex(ValueError, 'requested batch'):
                publish(center, self.batch, alpha.piece_id, beta_other.piece_id, 'v1')
            self.assertEqual(self.counts(center), (0, 0))
            self.assertEqual(self.exchange_counts(center), (2, 2))
        beta = self.admitted_revision(self.seed('beta'))
        self.assertEqual(self.finish(alpha, beta).assessment.as_data(), BAND)

    def test_accept_identity_reuses_only_same_body(self):
        alpha_piece, _ = self.issue(self.seed('alpha'))
        original = self.admit(alpha_piece)
        body = canonical_envelope_body(seal_piece(alpha_piece))
        body_with_space = json.dumps(json.loads(body), indent=2)
        different = replace(alpha_piece, evidence=CalibrationEvidence(empty=True))
        conflict = canonical_envelope_body(seal_piece(different))
        with self.center() as center:
            self.assertEqual(accept(center, self.batch, body_with_space), original)
            with self.assertRaisesRegex(ValueError, 'different envelope'):
                accept(center, self.batch, conflict)
            self.assertEqual(get_accepted_piece(center, original.piece_id), original)
            self.assertEqual(self.exchange_counts(center), (1, 1))
        beta = self.admitted_revision(self.seed('beta'))
        self.assertEqual(self.finish(original, beta).assessment.as_data(), BAND)

    def test_role_mismatch_cannot_enter_center(self):
        piece, _ = self.issue(self.seed('alpha'))
        wrong_role = canonical_envelope_body(seal_piece(replace(piece, role='beta')))
        with self.center() as center:
            with self.assertRaisesRegex(ValueError, 'role conflicts'):
                accept(center, self.batch, wrong_role)
            self.assertEqual(self.exchange_counts(center), (0, 0))
        self.assertEqual(self.admit(piece).piece, piece)

    def test_bad_envelope_leaves_catalog_empty(self):
        piece, _ = self.issue(self.seed('alpha'))
        body = canonical_envelope_body(seal_piece(piece))
        decoded = json.loads(body)
        with self.center() as center:
            for changes in (
                {'version': True}, {'issue_id': 'wrong:00000000000000000000000000000000'},
                {'evidence': {'empty': False, 'planes': [['1', '0', '1/0']]}},
                {'evidence': {'empty': True, 'planes': [['1', '0', '0']]}},
            ):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    accept(center, self.batch, json.dumps(decoded | changes))
            with self.assertRaisesRegex(ValueError, 'duplicate exchange field'):
                accept(center, self.batch, body[:-1] + ',"version":1}')
            self.assertEqual(self.exchange_counts(center), (0, 0))

    def test_missing_or_repeated_parent_cannot_publish(self):
        alpha, beta = self.pair()
        with self.workspace.offline(), self.center() as center:
            with self.assertRaises(LookupError):
                publish(center, self.batch, alpha.piece_id, 'missing', 'v1')
            with self.assertRaisesRegex(ValueError, 'both registered stations'):
                publish(center, self.batch, alpha.piece_id, alpha.piece_id, 'v1')
            with self.assertRaisesRegex(ValueError, 'unknown gear policy'):
                publish(center, self.batch, alpha.piece_id, beta.piece_id, 'missing')
            self.assertEqual(self.counts(center), (0, 0))
