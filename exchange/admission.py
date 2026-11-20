from exchange.catalog import lock_piece
from exchange.envelope import decode_envelope
from exchange.registry import get_roster


def accept(connection, batch, body):
    roster = get_roster(connection, batch)
    envelope = decode_envelope(body)
    piece = envelope.piece
    if piece.batch != batch:
        raise ValueError('envelope belongs to a different batch')
    if roster.role_for(piece.station) != piece.role:
        raise ValueError('envelope role conflicts with batch roster')
    return lock_piece(connection, envelope)
