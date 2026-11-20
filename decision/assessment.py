from dataclasses import dataclass

from decision.eligibility import guaranteed_readings
from decision.intervals import RationalInterval, decode_intervals, encode_intervals, subtract_intervals
from decision.joint_region import build_joint_region, supported_readings
from decision.policy import GearPolicy
from exchange.pairing import AcceptedPair


@dataclass(frozen=True)
class Assessment:
    evidence_domain: tuple[RationalInterval, ...]
    low: tuple[RationalInterval, ...]
    high: tuple[RationalInterval, ...]
    manual: tuple[RationalInterval, ...]

    def as_data(self):
        return {
            'evidence_domain': encode_intervals(self.evidence_domain),
            'low': encode_intervals(self.low), 'high': encode_intervals(self.high),
            'manual': encode_intervals(self.manual),
        }

    @classmethod
    def from_data(cls, data):
        return cls(*(decode_intervals(data[field]) for field in ('evidence_domain', 'low', 'high', 'manual')))


def assess(pair: AcceptedPair, policy: GearPolicy):
    region = build_joint_region(pair.alpha.piece.evidence, pair.beta.piece.evidence)
    domain = supported_readings(region)
    low = guaranteed_readings(region, policy.low, domain)
    high = guaranteed_readings(region, policy.high, domain)
    return Assessment(domain, low, high, subtract_intervals(domain, (*low, *high)))
