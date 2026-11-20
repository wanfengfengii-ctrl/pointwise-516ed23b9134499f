import json
from dataclasses import asdict, dataclass

from decision.assessment import Assessment
from decision.policy import GearPolicy
from intake.batches import require_name
from reports.receipts import PublishReceipt


@dataclass(frozen=True)
class ParentPiece:
    piece_id: str
    issue_id: str
    revision_id: str
    station: str
    role: str

    @classmethod
    def from_accepted(cls, accepted):
        source = accepted.piece
        return cls(accepted.piece_id, source.issue_id, source.revision_id, source.station, source.role)


@dataclass(frozen=True)
class SignedReport:
    report_id: str
    batch: str
    parents: tuple[ParentPiece, ParentPiece]
    policy: GearPolicy
    assessment: Assessment
    receipt: PublishReceipt


def initialize_report_store(connection):
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS signed_reports (
            report_id TEXT PRIMARY KEY,
            batch TEXT NOT NULL REFERENCES batch_roster(batch),
            parents TEXT NOT NULL,
            policy TEXT NOT NULL,
            assessment TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS publish_receipts (
            report_id TEXT PRIMARY KEY REFERENCES signed_reports(report_id),
            receipt_id TEXT NOT NULL UNIQUE
        );
    ''')


def commit_report(connection, report):
    if report.receipt.report_id != report.report_id:
        raise ValueError('receipt does not belong to the report')
    parents = json.dumps([asdict(parent) for parent in report.parents], ensure_ascii=False, sort_keys=True)
    policy = json.dumps(report.policy.as_data(), sort_keys=True)
    assessment = json.dumps(report.assessment.as_data(), sort_keys=True)
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('INSERT INTO signed_reports VALUES (?, ?, ?, ?, ?)',
                           (report.report_id, report.batch, parents, policy, assessment))
        connection.execute('INSERT INTO publish_receipts VALUES (?, ?)',
                           (report.report_id, report.receipt.receipt_id))
    return report


def load_report(connection, report_id):
    require_name(report_id, 'report ID')
    row = connection.execute(
        '''SELECT s.batch, s.parents, s.policy, s.assessment, r.receipt_id
           FROM signed_reports AS s JOIN publish_receipts AS r USING (report_id)
           WHERE s.report_id = ?''', (report_id,),
    ).fetchone()
    if row is None:
        raise LookupError('published report not found')
    batch, parents, policy, assessment, receipt_id = row
    return SignedReport(
        report_id, batch, tuple(ParentPiece(**item) for item in json.loads(parents)),
        GearPolicy.from_data(json.loads(policy)), Assessment.from_data(json.loads(assessment)),
        PublishReceipt(receipt_id, report_id),
    )
