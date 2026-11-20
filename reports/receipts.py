from dataclasses import dataclass


@dataclass(frozen=True)
class PublishReceipt:
    receipt_id: str
    report_id: str


def make_publish_receipt(report_id):
    return PublishReceipt(f'publish:{report_id}', report_id)
