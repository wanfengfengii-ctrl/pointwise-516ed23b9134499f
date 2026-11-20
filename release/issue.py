from intake.batches import get_batch, require_name
from intake.revisions import get_revision
from release.calibration import build_calibration
from release.catalog import store_issue
from release.projection import project_station_calibration


def freeze(store, batch, station, revision_id):
    require_name(revision_id, 'revision ID')
    spec = get_batch(store, batch, station)
    revision = get_revision(store, batch, station, revision_id)
    evidence = project_station_calibration(build_calibration(revision))
    return store_issue(store, spec, revision.revision_id, evidence)
