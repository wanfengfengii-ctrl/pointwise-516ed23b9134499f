import json
from dataclasses import dataclass
from uuid import uuid4

from intake.batches import require_name
from intake.store import station_transaction
from release.evidence import StationPiece, decode_evidence, encode_evidence


@dataclass(frozen=True)
class IssueReceipt:
    receipt_id: str
    issue_id: str


def initialize_issue_catalog(store):
    store.connection.executescript('''
        CREATE TABLE IF NOT EXISTS station_issues (
            issue_id TEXT PRIMARY KEY,
            batch TEXT NOT NULL,
            station TEXT NOT NULL,
            role TEXT NOT NULL,
            revision_id TEXT NOT NULL REFERENCES measure_revisions(revision_id),
            evidence TEXT NOT NULL,
            FOREIGN KEY (batch, station) REFERENCES station_batches(batch, station)
        );
        CREATE TABLE IF NOT EXISTS issue_receipts (
            issue_id TEXT PRIMARY KEY REFERENCES station_issues(issue_id),
            receipt_id TEXT NOT NULL UNIQUE
        );
    ''')


def store_issue(store, spec, revision_id, evidence):
    issue_id = f'{spec.station}:{uuid4().hex}'
    receipt = IssueReceipt(f'issue:{issue_id}', issue_id)
    piece = StationPiece(issue_id, spec.batch, spec.station, spec.role, revision_id, evidence)
    with station_transaction(store) as connection:
        connection.execute(
            'INSERT INTO station_issues VALUES (?, ?, ?, ?, ?, ?)',
            (issue_id, piece.batch, piece.station, piece.role, revision_id,
             json.dumps(encode_evidence(evidence), sort_keys=True, separators=(',', ':'))),
        )
        connection.execute('INSERT INTO issue_receipts VALUES (?, ?)', (issue_id, receipt.receipt_id))
    return piece, receipt


def reclaim_issue(store, issue_id):
    require_name(issue_id, 'issue ID')
    row = store.connection.execute(
        '''SELECT i.batch, i.station, i.role, i.revision_id, i.evidence, r.receipt_id
           FROM station_issues AS i JOIN issue_receipts AS r USING (issue_id)
           WHERE i.issue_id = ?''', (issue_id,),
    ).fetchone()
    if row is None:
        raise LookupError('station issue not found')
    batch, station, role, revision_id, evidence, receipt_id = row
    return (
        StationPiece(issue_id, batch, station, role, revision_id, decode_evidence(json.loads(evidence))),
        IssueReceipt(receipt_id, issue_id),
    )
