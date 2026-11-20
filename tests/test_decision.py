from fractions import Fraction

from reports.retrieve import read
from tests.support import BAND, DIAGONAL, DOMAIN, EMPTY, ShiftCase, constraint, measurement, scenario


class DecisionTests(ShiftCase):
    def test_offline_banded_calibration(self):
        alpha, beta = self.pair()
        report = self.finish(beta, alpha)
        actual = report.assessment.as_data()
        self.assertEqual(actual, BAND, 'GEAR_SELECTION_MISMATCH')
        expected_parents = (alpha.piece_id, beta.piece_id)
        actual_parents = tuple(parent.piece_id for parent in report.parents)
        self.assertEqual(actual_parents, expected_parents)
        with self.workspace.offline(), self.center() as center:
            reclaimed = read(center, report.report_id)
        self.assertEqual(reclaimed, report)
        scenario('check_offline', {'alpha': 'q-p=t, |t|<=1/4', 'beta': '[0,1]^2'}, BAND, actual,
                 True, reclaimed == report and actual_parents == expected_parents,
                 ['release/projection.py', 'decision/joint_region.py', 'decision/eligibility.py', 'reports/publish.py'],
                 'q 的上界是 min(1,p+1/4)，下界是 max(0,p−1/4)，分别与 1/2 比较')

    def test_same_marginals_yield_different_offline_decisions(self):
        band, beta = self.pair()
        square = self.admitted_revision(self.seed('alpha', [measurement('square')]))
        band_result = self.finish(band, beta).assessment.as_data()
        square_result = self.finish(square, beta).assessment.as_data()
        self.assertEqual(band_result, BAND)
        self.assertEqual(square_result, {'evidence_domain': DOMAIN, 'low': [], 'high': [], 'manual': DOMAIN})

    def test_universal_guarantee_excludes_midpoint_but_accepts_limits(self):
        alpha, beta = self.pair()
        self.assertTrue(alpha.piece.evidence.contains('1/2', '1/4'))
        self.assertTrue(alpha.piece.evidence.contains('1/2', '3/4'))
        decision = self.finish(alpha, beta).assessment
        self.assertEqual([span.contains(Fraction(1, 2)) for span in decision.low + decision.high],
                         [False, False], 'GEAR_SELECTION_MISMATCH')
        self.assertTrue(any(span.contains(Fraction(1, 4)) for span in decision.low))
        self.assertTrue(any(span.contains(Fraction(3, 4)) for span in decision.high))
        self.assertTrue(any(span.contains(Fraction(1, 2)) for span in decision.manual))

    def test_same_alpha_with_diagonal_beta(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        beta = self.admitted_revision(self.seed('beta', [measurement('diagonal', constraint(-1, 1, 0, 0))]))
        self.assertEqual(self.finish(alpha, beta).assessment.as_data(), DIAGONAL)

    def test_exact_limit_keeps_singleton(self):
        alpha, beta = self.pair(beta_measurements=[measurement('fixed', constraint(1, 0, 0, '1/2'),
                                                              constraint(0, 1, 0, '1/2'))])
        report = self.finish(alpha, beta)
        point = [['1/2', '1/2', True, True]]
        expected = {'evidence_domain': point, 'low': point, 'high': point, 'manual': []}
        actual = report.assessment.as_data()
        self.assertEqual(actual, expected)
        with self.workspace.offline(), self.center() as center:
            stored = read(center, report.report_id)
        self.assertEqual(stored, report)
        scenario('check_point', {'p': '1/2', 'q': '1/2'}, expected, actual, True, stored == report,
                 ['decision/joint_region.py', 'decision/eligibility.py', 'decision/intervals.py', 'reports/store.py'],
                 '唯一 q 与两档扣除量的距离均为 1/2')

    def test_disagreeing_stations_publish_empty(self):
        alpha, beta = self.pair([measurement('zero', constraint(0, 1, 0, 0))],
                                [measurement('one', constraint(0, 1, 0, 1))])
        report = self.finish(alpha, beta)
        self.assertEqual(report.assessment.as_data(), EMPTY)
        self.assertEqual(tuple(parent.piece_id for parent in report.parents), (alpha.piece_id, beta.piece_id))
        with self.center() as center:
            self.assertEqual(self.counts(center), (1, 1))
            self.assertEqual(read(center, report.report_id), report)

    def test_disconnected_gear_ranges_preserve_both_closed_limits(self):
        alpha, beta = self.pair([measurement('roof', constraint(-2, 1, 0, 0, '<='),
                                            constraint(2, 1, 0, 2, '<='))])
        self.assertEqual(self.finish(alpha, beta).assessment.as_data(), {
            'evidence_domain': DOMAIN,
            'low': [['0', '1/4', True, True], ['3/4', '1', True, True]],
            'high': [], 'manual': [['1/4', '3/4', False, False]],
        })

    def test_open_manual_ranges_leave_supported_isolated_safe_reading(self):
        # q >= max(0, 4*p-2, 2-4*p) and q <= 1. Outside [1/4,3/4] there is no evidence.
        alpha, beta = self.pair([measurement('floor', constraint(4, -1, 0, 2, '<='),
                                            constraint(-4, -1, 0, -2, '<='))])
        result = self.finish(alpha, beta).assessment.as_data()
        self.assertEqual(result, {
            'evidence_domain': [['1/4', '3/4', True, True]],
            'low': [],
            'high': [['1/4', '3/8', True, True], ['5/8', '3/4', True, True]],
            'manual': [['3/8', '5/8', False, False]],
        })

    def test_private_drift_is_eliminated_from_frozen_relation(self):
        # The frozen relation must reflect q-p=t jointly with |t|<=1/4, not the
        # independent coordinate spans of the two stations.
        alpha, _ = self.pair()
        self.assertTrue(alpha.piece.evidence.contains('1/2', '1/4'))
        self.assertTrue(alpha.piece.evidence.contains('1/2', '3/4'))
        self.assertFalse(alpha.piece.evidence.contains('0', 1))
        self.assertFalse(alpha.piece.evidence.contains('1', 0))
        self.assertFalse(alpha.piece.evidence.contains('1/2', 0))
        scenario('check_projection.private_drift', {'alpha': 'q-p=t, |t|<=1/4'},
                 [True, True, False, False], [alpha.piece.evidence.contains('1/2', '1/4'),
                                              alpha.piece.evidence.contains('1/2', '3/4'),
                                              alpha.piece.evidence.contains('0', 1),
                                              alpha.piece.evidence.contains('1', 0)],
                 True, True, ['release/projection.py'],
                 'Fourier-Motzkin 消去 t 后 q-p 落在 [-1/4,1/4]')

    def test_midpoint_needs_manual_under_universal_guarantee(self):
        alpha, beta = self.pair()
        decision = self.finish(alpha, beta).assessment
        midpoint = Fraction(1, 2)
        self.assertFalse(any(span.contains(midpoint) for span in decision.low))
        self.assertFalse(any(span.contains(midpoint) for span in decision.high))
        self.assertTrue(any(span.contains(midpoint) for span in decision.manual))

    def test_flat_slice_on_limit_is_usable_throughout(self):
        # A station that pins q = 1/2 for every p leaves residual exactly 1/2
        # for both gears, so the whole domain is usable and nothing is manual.
        alpha = self.admitted_revision(self.seed('alpha', [
            measurement('flat', constraint(0, 1, 0, '1/2'), constraint(0, 1, 0, '1/2', '>='))]))
        beta = self.admitted_revision(self.seed('beta'))
        decision = self.finish(alpha, beta).assessment.as_data()
        self.assertEqual(decision, {
            'evidence_domain': DOMAIN, 'low': DOMAIN, 'high': DOMAIN, 'manual': [],
        })
