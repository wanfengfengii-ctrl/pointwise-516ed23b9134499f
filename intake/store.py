import sqlite3
from contextlib import contextmanager


class StationStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA foreign_keys = ON')

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def initialize_station_store(store):
    store.connection.executescript('''
        CREATE TABLE IF NOT EXISTS station_batches (
            batch TEXT NOT NULL,
            station TEXT NOT NULL,
            role TEXT NOT NULL,
            scales TEXT NOT NULL,
            current_revision TEXT,
            PRIMARY KEY (batch, station)
        );
        CREATE TABLE IF NOT EXISTS measure_revisions (
            revision_id TEXT PRIMARY KEY,
            batch TEXT NOT NULL,
            station TEXT NOT NULL,
            parent_revision TEXT REFERENCES measure_revisions(revision_id),
            drift TEXT NOT NULL,
            measurements TEXT NOT NULL,
            FOREIGN KEY (batch, station) REFERENCES station_batches(batch, station)
        );
    ''')


@contextmanager
def station_transaction(store):
    connection = store.connection
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        yield connection
