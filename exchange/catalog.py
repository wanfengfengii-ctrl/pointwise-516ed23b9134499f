from dataclasses import dataclass
from uuid import uuid4

from exchange.envelope import ExchangeEnvelope, canonical_envelope_body, decode_envelope
from intake.batches import require_name


@dataclass(frozen=True)
class AcceptanceReceipt:
    receipt_id: str
    piece_id: str
    issue_id: str


@dataclass(frozen=True)
class AcceptedPiece:
    piece_id: str
    envelope: ExchangeEnvelope
    receipt: AcceptanceReceipt

    @property
    def piece(self):
        return self.envelope.piece


def initialize_exchange_catalog(connection):
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS center_pieces (
            piece_id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL UNIQUE,
            batch TEXT NOT NULL REFERENCES batch_roster(batch),
            body TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS acceptance_receipts (
            piece_id TEXT PRIMARY KEY REFERENCES center_pieces(piece_id),
            receipt_id TEXT NOT NULL UNIQUE
        );
    ''')


def get_accepted_piece(connection, piece_id):
    require_name(piece_id, 'center piece ID')
    row = connection.execute(
        '''SELECT p.issue_id, p.body, r.receipt_id
           FROM center_pieces AS p JOIN acceptance_receipts AS r USING (piece_id)
           WHERE p.piece_id = ?''', (piece_id,),
    ).fetchone()
    if row is None:
        raise LookupError('center piece not found')
    issue_id, body, receipt_id = row
    return AcceptedPiece(piece_id, decode_envelope(body), AcceptanceReceipt(receipt_id, piece_id, issue_id))


def lock_piece(connection, envelope):
    body = canonical_envelope_body(envelope)
    source = envelope.piece
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(
            'SELECT piece_id, body FROM center_pieces WHERE issue_id = ?', (source.issue_id,),
        ).fetchone()
        if row is not None:
            piece_id, previous_body = row
            if previous_body != body:
                raise ValueError('issue ID already locked to a different envelope')
            return get_accepted_piece(connection, piece_id)
        piece_id = f'center:{uuid4().hex}'
        receipt = AcceptanceReceipt(f'accept:{piece_id}', piece_id, source.issue_id)
        connection.execute('INSERT INTO center_pieces VALUES (?, ?, ?, ?)',
                           (piece_id, source.issue_id, source.batch, body))
        connection.execute('INSERT INTO acceptance_receipts VALUES (?, ?)', (piece_id, receipt.receipt_id))
    return AcceptedPiece(piece_id, envelope, receipt)
