import json
from dataclasses import asdict

from reports.retrieve import read


def export_report(connection, report_id):
    report = read(connection, report_id)
    document = {
        'report_id': report.report_id,
        'batch': report.batch,
        'parents': [asdict(parent) for parent in report.parents],
        'policy': report.policy.as_data(),
        'assessment': report.assessment.as_data(),
        'receipt': asdict(report.receipt),
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
