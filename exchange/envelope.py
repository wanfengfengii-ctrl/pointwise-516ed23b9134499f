import json
import re
from dataclasses import dataclass

from intake.batches import ROLES, require_name
from release.evidence import StationPiece, decode_evidence, encode_evidence


@dataclass(frozen=True)
class ExchangeEnvelope:
    piece: StationPiece
    version: int = 1


def seal_piece(piece):
    return ExchangeEnvelope(piece)


def canonical_envelope_body(envelope):
    piece = envelope.piece
    return json.dumps({
        'version': envelope.version, 'issue_id': piece.issue_id,
        'batch': piece.batch, 'station': piece.station, 'role': piece.role,
        'revision_id': piece.revision_id, 'evidence': encode_evidence(piece.evidence),
    }, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate exchange field')
        result[key] = value
    return result


def _check_station_id(value, station, label):
    value = require_name(value, label)
    prefix, separator, suffix = value.rpartition(':')
    if not separator or prefix != station or not re.fullmatch(r'[0-9a-f]{32}', suffix):
        raise ValueError(f'{label} does not match declared station namespace')


def decode_envelope(body):
    if not isinstance(body, str):
        raise ValueError('exchange envelope must be JSON text')
    raw = json.loads(body, object_pairs_hook=_unique_object)
    fields = {'version', 'issue_id', 'batch', 'station', 'role', 'revision_id', 'evidence'}
    if not isinstance(raw, dict) or raw.keys() != fields:
        raise ValueError('invalid exchange envelope fields')
    if type(raw['version']) is not int or raw['version'] != 1:
        raise ValueError('unsupported exchange envelope version')
    station = require_name(raw['station'], 'station')
    batch = require_name(raw['batch'], 'batch')
    if raw['role'] not in ROLES:
        raise ValueError('invalid exchange role')
    _check_station_id(raw['issue_id'], station, 'issue ID')
    _check_station_id(raw['revision_id'], station, 'revision ID')
    evidence = decode_evidence(raw['evidence'])
    return ExchangeEnvelope(StationPiece(raw['issue_id'], batch, station, raw['role'], raw['revision_id'], evidence))
