import json
import sqlite3
from dataclasses import asdict

from exchange.catalog import get_accepted_piece
from exchange.registry import get_roster
from intake.revisions import get_revision
from release.catalog import reclaim_issue
from reports.export import export_report
from reports.publish import publish
from reports.retrieve import read
from reports.shift import initialize_workspaces, run_shift
from tests.support import BAND, DIAGONAL, ShiftCase, scenario


class ReportTests(ShiftCase):
    def test_publish_rollback_and_retry(self):
        alpha, beta = self.pair()
        with self.center() as center:
            center.execute('''CREATE TRIGGER fail_report BEFORE INSERT ON signed_reports
                              BEGIN SELECT RAISE(ABORT, 'report write rejected'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'report write rejected'):
            self.finish(alpha, beta)
        with self.center() as center:
            self.assertEqual(self.counts(center), (0, 0))
            center.execute('DROP TRIGGER fail_report')
        report = self.finish(alpha, beta)
        self.assertEqual(report.assessment.as_data(), BAND)
        with self.center() as center:
            self.assertEqual(self.counts(center), (1, 1))
            self.assertEqual(read(center, report.report_id), report)

    def test_receipt_write_failure_rolls_back_report_row(self):
        alpha, beta = self.pair()
        with self.center() as center:
            center.execute('''CREATE TRIGGER fail_receipt BEFORE INSERT ON publish_receipts
                BEGIN
                    SELECT CASE WHEN EXISTS (
                        SELECT 1 FROM signed_reports WHERE report_id = NEW.report_id
                    ) THEN RAISE(ABORT, 'receipt rejected after report insert')
                      ELSE RAISE(ABORT, 'report row not yet written') END;
                END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt rejected after report insert'):
            self.finish(alpha, beta)
        with self.center() as center:
            failed_counts = self.counts(center)
            self.assertEqual(failed_counts, (0, 0))
            center.execute('DROP TRIGGER fail_receipt')
        report = self.finish(alpha, beta)
        with self.center() as center:
            retry_counts = self.counts(center)
            self.assertEqual(retry_counts, (1, 1))
            self.assertEqual(read(center, report.report_id).receipt, report.receipt)
        scenario('check_rollback.receipt_write_failure', {'failure': 'receipt insert after report insert'},
                 (0, 0), failed_counts, (1, 1), retry_counts, ['reports/publish.py', 'reports/store.py'],
                 'SQLite 触发器确认定稿行已经在事务内出现，再拒绝回执；新连接分别计数')

    def test_revision_and_reopen_preserve_original(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        beta_revision = self.seed('beta')
        beta = self.admitted_revision(beta_revision)
        original = self.finish(alpha, beta)
        self.assertEqual(original.assessment.as_data(), BAND)
        with self.center() as center:
            original_export = export_report(center, original.report_id)
        corrected_revision = self.correct_beta(beta_revision)
        corrected = self.admitted_revision(corrected_revision)
        updated = self.finish(alpha, corrected)
        self.assertNotEqual(updated.report_id, original.report_id)
        self.assertEqual(updated.assessment.as_data(), DIAGONAL)
        self.assertEqual(updated.parents[1].revision_id, corrected_revision.revision_id)
        with self.workspace.offline(), self.center() as center:
            old = read(center, original.report_id)
            new = read(center, updated.report_id)
            old_export = export_report(center, original.report_id)
            new_export = json.loads(export_report(center, updated.report_id))
            self.assertEqual(self.counts(center), (2, 2))
        self.assertEqual(old, original)
        self.assertEqual(new, updated)
        self.assertEqual(old_export, original_export)
        snapshot = json.loads(old_export)
        self.assertEqual(snapshot['assessment'], BAND)
        self.assertEqual(snapshot['parents'], [asdict(parent) for parent in original.parents])
        self.assertEqual(snapshot['receipt'], asdict(original.receipt))
        self.assertEqual(snapshot['policy'], {
            'name': 'v1', 'low': {'name': 'low', 'deduction': '0', 'residual_limit': '1/2'},
            'high': {'name': 'high', 'deduction': '1', 'residual_limit': '1/2'},
        })
        self.assertEqual(new_export['receipt']['report_id'], updated.report_id)
        self.assertNotEqual(new_export['receipt'], snapshot['receipt'])
        scenario('check_history.export_snapshot', {'original_beta': 'unit square', 'corrected_beta': 'q=p'},
                 BAND, snapshot['assessment'], [True, True], [old_export == original_export, new == updated],
                 ['reports/store.py', 'reports/retrieve.py', 'reports/export.py'],
                 '先保存原次签发导出，勘误后重开中心按两个原号对照')

    def test_explicit_old_freeze_after_correction(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        base = self.seed('beta')
        current = self.correct_beta(base)
        old_piece, _ = self.issue(base)
        new_piece, _ = self.issue(current)
        self.assertEqual(old_piece.revision_id, base.revision_id)
        self.assertEqual(new_piece.revision_id, current.revision_id)
        self.assertTrue(old_piece.evidence.contains(0, 1))
        self.assertFalse(new_piece.evidence.contains(0, 1))
        self.assertEqual(self.finish(alpha, self.admit(old_piece)).assessment.as_data(), BAND)
        self.assertEqual(self.finish(alpha, self.admit(new_piece)).assessment.as_data(), DIAGONAL)

    def test_reinitialize_preserves_user_data_and_both_reports(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        base = self.seed('beta')
        old_piece, old_receipt = self.issue(base)
        old_accepted = self.admit(old_piece)
        before = self.finish(alpha, old_accepted)
        current = self.correct_beta(base)
        new_piece, new_receipt = self.issue(current)
        new_accepted = self.admit(new_piece)
        after = self.finish(alpha, new_accepted)
        again = initialize_workspaces(self.root, reversed(tuple(self.specs.values())))
        self.assertEqual(again, self.workspace)
        with self.station('beta') as store:
            self.assertEqual(get_revision(store, self.batch, current.station), current)
            self.assertEqual(get_revision(store, self.batch, base.station, base.revision_id), base)
            self.assertEqual(reclaim_issue(store, old_piece.issue_id), (old_piece, old_receipt))
            self.assertEqual(reclaim_issue(store, new_piece.issue_id), (new_piece, new_receipt))
            self.assertEqual(self.issue_counts(store), (2, 2))
        with self.workspace.offline(), self.center() as center:
            self.assertEqual(get_roster(center, self.batch), self.workspace.roster)
            self.assertEqual(get_accepted_piece(center, old_accepted.piece_id), old_accepted)
            self.assertEqual(get_accepted_piece(center, new_accepted.piece_id), new_accepted)
            self.assertEqual(read(center, before.report_id), before)
            self.assertEqual(read(center, after.report_id), after)
            self.assertEqual(self.counts(center), (2, 2))

    def test_unknown_report_does_not_affect_published_history(self):
        alpha = self.admitted_revision(self.seed('alpha'))
        beta = self.seed('beta')
        first = self.finish(alpha, self.admitted_revision(beta))
        second = self.finish(alpha, self.admitted_revision(self.correct_beta(beta)))
        with self.workspace.offline(), self.center() as center:
            with self.assertRaisesRegex(LookupError, 'not found'):
                read(center, 'report:unknown')
            with self.assertRaisesRegex(LookupError, 'not found'):
                export_report(center, 'report:unknown')
            self.assertEqual(read(center, first.report_id), first)
            self.assertEqual(read(center, second.report_id), second)
            self.assertEqual(self.counts(center), (2, 2))

    def test_demo_runs_through_original_and_corrected_signoff(self):
        result = run_shift(self.root / 'demo', self.sample)
        self.assertEqual(result['before']['assessment'], BAND)
        self.assertEqual(result['after']['assessment'], DIAGONAL)
        self.assertTrue(result['original_reclaimed'])
        self.assertEqual(result['before']['parents'][0], result['after']['parents'][0])
        self.assertNotEqual(result['before']['parents'][1], result['after']['parents'][1])
