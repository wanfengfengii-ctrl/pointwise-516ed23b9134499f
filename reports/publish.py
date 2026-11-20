from uuid import uuid4

from decision.assessment import assess
from decision.policy import resolve_policy
from exchange.pairing import resolve_pair
from reports.receipts import make_publish_receipt
from reports.store import ParentPiece, SignedReport, commit_report


def publish(connection, batch, first_id, second_id, policy_name):
    pair = resolve_pair(connection, batch, first_id, second_id)
    policy = resolve_policy(policy_name)
    assessment = assess(pair, policy)
    report_id = f'report:{uuid4().hex}'
    report = SignedReport(
        report_id, pair.batch, tuple(ParentPiece.from_accepted(item) for item in pair.pieces), policy,
        assessment, make_publish_receipt(report_id),
    )
    return commit_report(connection, report)
