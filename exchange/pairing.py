from dataclasses import dataclass

from exchange.catalog import AcceptedPiece, get_accepted_piece
from exchange.registry import get_roster


@dataclass(frozen=True)
class AcceptedPair:
    batch: str
    alpha: AcceptedPiece
    beta: AcceptedPiece

    @property
    def pieces(self):
        return self.alpha, self.beta


def resolve_pair(connection, batch, first_id, second_id):
    roster = get_roster(connection, batch)
    first = get_accepted_piece(connection, first_id)
    second = get_accepted_piece(connection, second_id)
    if first.piece.batch != batch or second.piece.batch != batch:
        raise ValueError('both parents must belong to the requested batch')
    stations = {item.piece.station: item for item in (first, second)}
    if stations.keys() != {roster.alpha_station, roster.beta_station}:
        raise ValueError('parents must cover both registered stations')
    for station, item in stations.items():
        if roster.role_for(station) != item.piece.role:
            raise ValueError('parent role conflicts with batch roster')
    return AcceptedPair(batch, stations[roster.alpha_station], stations[roster.beta_station])
