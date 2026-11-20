from fractions import Fraction

from intake.revisions import get_revision, record
from release.catalog import reclaim_issue
from release.issue import freeze
from tests.support import ShiftCase, constraint, measurement, scenario


class RevisionTests(ShiftCase):
    def test_invalid_measurement_leaves_prior_revision(self):
        previous = self.seed('alpha')
        inputs = [measurement('valid', constraint(0, 1, 0, '1/2')),
                  measurement('invalid', constraint(0, 1, 0, '1/0'))]
        with self.station('alpha') as store:
            with self.assertRaisesRegex(ValueError, 'rational'):
                record(store, self.batch, previous.station, inputs, drift=self.inputs['alpha']['drift'])
            current = get_revision(store, self.batch, previous.station)
            self.assertEqual(current, previous)
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM measure_revisions').fetchone(), (1,))
            piece, _ = freeze(store, self.batch, previous.station, previous.revision_id)
        self.assertEqual(piece.revision_id, previous.revision_id)
        self.assertTrue(piece.evidence.contains(0, 0))

    def test_equivalent_units_survive_bad_record(self):
        nm = measurement('reference', constraint(0, 1, 0, '1', units=('normalized', 'nm', 'normalized')),
                         value='1', unit='nm')
        um = measurement('reference', constraint(0, 1, 0, '1/1000', units=('normalized', 'μm', 'normalized')),
                         value='1/1000', unit='μm')
        first = self.seed('alpha', [nm])
        second = self.seed('alpha', [um])
        first_measurement, = first.measurements
        second_measurement, = second.measurements
        self.assertEqual(first_measurement.normalized_value, Fraction(1, 1000))
        self.assertEqual(second_measurement.normalized_value, Fraction(1, 1000))
        self.assertEqual(first_measurement.constraints, second_measurement.constraints)
        self.assertEqual(first_measurement.raw_constraints[0].bound, '1')
        self.assertEqual(second_measurement.raw_constraints[0].bound, '1/1000')
        with self.station('alpha') as store:
            with self.assertRaisesRegex(ValueError, 'rational'):
                record(store, self.batch, second.station, [measurement('bad', value='1/0')],
                       drift=self.inputs['alpha']['drift'])
            self.assertEqual(get_revision(store, self.batch, second.station), second)
        left, _ = self.issue(first)
        right, _ = self.issue(second)
        self.assertEqual(left.evidence, right.evidence)
        supported = [piece.evidence.contains('1/2', '1/1000') for piece in (left, right)]
        self.assertEqual(supported, [True, True])
        self.assertFalse(left.evidence.contains('1/2', '1/999'))
        scenario('check_bad_record.equivalent_units', ['1 nm', '1/1000 μm'], ['1/1000'] * 2,
                 [str(first_measurement.normalized_value), str(second_measurement.normalized_value)],
                 [True, True], supported, ['intake/normalization.py', 'release/projection.py'],
                 '1 μm 的批次跨度等于 1000 nm')

    def test_wrong_revision_parent_keeps_current_and_issue(self):
        alpha = self.seed('alpha')
        beta = self.seed('beta')
        old = self.issue(beta)
        with self.station('beta') as store:
            # Register the other station in this catalog to test a present, wrongly scoped parent.
            alpha_spec = self.specs['alpha']
            from intake.batches import register_batch
            register_batch(store, alpha_spec)
            foreign = record(store, self.batch, alpha.station, self.inputs['alpha']['measurements'],
                             drift=self.inputs['alpha']['drift'])
            with self.assertRaisesRegex(ValueError, 'different batch or station'):
                record(store, self.batch, beta.station, self.sample['beta_correction'], parent_revision=foreign.revision_id)
            with self.assertRaises(LookupError):
                record(store, self.batch, beta.station, self.sample['beta_correction'], parent_revision=alpha.revision_id)
            with self.assertRaisesRegex(ValueError, 'absent from its parent'):
                record(store, self.batch, beta.station, [measurement('other')], parent_revision=beta.revision_id)
            self.assertEqual(get_revision(store, self.batch, beta.station), beta)
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM measure_revisions').fetchone(), (2,))
            self.assertEqual(reclaim_issue(store, old[0].issue_id), old)

    def test_correction_keeps_untouched_measurement_origin(self):
        base = self.seed('beta', [measurement('reference-B'), measurement('other-reference')])
        corrected = self.correct_beta(base)
        first, second = corrected.measurements
        self.assertEqual(corrected.parent_revision, base.revision_id)
        self.assertEqual(first.origin_revision, corrected.revision_id)
        self.assertEqual(second, base.measurements[1])
        self.assertEqual(second.origin_revision, base.revision_id)
        with self.station('beta') as store:
            self.assertEqual(get_revision(store, self.batch, base.station, base.revision_id), base)
            self.assertEqual(get_revision(store, self.batch, base.station), corrected)
