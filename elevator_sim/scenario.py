"""Immutable external demand, generated once and replayed by every policy."""
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Optional

from .traffic import TrafficGenerator
import config


@dataclass(frozen=True)
class PassengerRequest:
    call_time: int
    origin: int
    target: int
    abandon_time: Optional[int] = None

    def validate(self, total_floors: int, duration: int) -> None:
        if not (0 <= self.call_time < duration):
            raise ValueError("request time must be inside the demand period")
        if not (1 <= self.origin <= total_floors and
                1 <= self.target <= total_floors and self.origin != self.target):
            raise ValueError("invalid request origin or target")
        if self.abandon_time is not None and self.abandon_time < self.call_time:
            raise ValueError("abandon time cannot precede call time")


def generate_requests(seed, duration=600, total_floors=10,
                      arrival_rate=0.15, abandon_probability=0.2):
    """Freeze demand before any elevator state or policy can influence it."""
    traffic = TrafficGenerator(
        total_floors, arrival_rate, abandon_probability,
        config.ABANDON_MIN_WAIT, config.ABANDON_MAX_WAIT, random.Random(seed))
    return tuple(PassengerRequest(p.call_time, p.origin, p.target, p.abandon_time)
                 for now in range(duration) for p in traffic.maybe_generate(now))


def scenario_document(requests):
    return {"schema_version": 1, "requests": [asdict(r) for r in requests]}


def scenario_hash(requests):
    encoded = json.dumps(scenario_document(requests), sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
