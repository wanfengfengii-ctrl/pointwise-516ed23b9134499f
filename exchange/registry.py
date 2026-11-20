from dataclasses import dataclass

from intake.batches import require_name


@dataclass(frozen=True)
class BatchRoster:
    batch: str
    alpha_station: str
    beta_station: str

    def __post_init__(self):
        require_name(self.batch, 'batch')
        require_name(self.alpha_station, 'alpha station')
        require_name(self.beta_station, 'beta station')
        if self.alpha_station == self.beta_station:
            raise ValueError('roster requires two distinct stations')

    def role_for(self, station):
        if station == self.alpha_station:
            return 'alpha'
        if station == self.beta_station:
            return 'beta'
        raise ValueError('station not in batch roster')


def initialize_registry(connection):
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS batch_roster (
                batch TEXT PRIMARY KEY, alpha_station TEXT NOT NULL, beta_station TEXT NOT NULL,
                CHECK (alpha_station <> beta_station)
            )
        ''')


def get_roster(connection, batch):
    require_name(batch, 'batch')
    row = connection.execute(
        'SELECT alpha_station, beta_station FROM batch_roster WHERE batch = ?', (batch,),
    ).fetchone()
    if row is None:
        raise LookupError('batch roster not found')
    return BatchRoster(batch, *row)


def register_roster(connection, roster):
    if not isinstance(roster, BatchRoster):
        raise ValueError('BatchRoster required')
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute(
            'INSERT INTO batch_roster VALUES (?, ?, ?) ON CONFLICT(batch) DO NOTHING',
            (roster.batch, roster.alpha_station, roster.beta_station),
        )
        if get_roster(connection, roster.batch) != roster:
            raise ValueError('roster conflicts with the existing batch registration')
    return roster
