from reports.store import load_report


def read(connection, report_id):
    return load_report(connection, report_id)
