"""Named reproducible simulation scenarios and JSON summary export."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path

from simulation.node_failures import run_node_failure_scenario
from simulation.packet_loss import run_packet_loss_scenario


@dataclass(frozen=True, slots=True)
class ScenarioReport:
    """Serializable summary of a reproducible simulation scenario run."""

    scenario_name: str
    seed: int
    parameters: dict[str, int | float | str | bool]
    messages_sent: int
    messages_delivered: int
    messages_failed: int
    delivery_ratio: float
    retransmissions: int
    modeled_latency_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_name, str) or not self.scenario_name.strip():
            raise ValueError("scenario_name must be a non-empty string")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_name": self.scenario_name,
            "seed": self.seed,
            "parameters": dict(self.parameters),
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "messages_failed": self.messages_failed,
            "delivery_ratio": round(self.delivery_ratio, 6),
            "retransmissions": self.retransmissions,
            "modeled_latency_seconds": round(self.modeled_latency_seconds, 6),
        }


SUPPORTED_SCENARIOS: frozenset[str] = frozenset(
    {"normal_operation", "random_packet_loss", "relay_node_failure"}
)


def run_named_scenario(name: str, *, seed: int = 42) -> ScenarioReport:
    """Execute one of the standard named scenarios with a deterministic seed."""
    if not isinstance(name, str) or name not in SUPPORTED_SCENARIOS:
        raise ValueError(f"unsupported scenario: {name!r}; expected one of {sorted(SUPPORTED_SCENARIOS)}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    if name == "normal_operation":
        result = run_packet_loss_scenario(
            loss_probability=0.0,
            message_count=20,
            max_retries=2,
            seed=seed,
        )
        return ScenarioReport(
            scenario_name=name,
            seed=seed,
            parameters={"loss_probability": 0.0, "message_count": 20, "max_retries": 2},
            messages_sent=result.metrics.messages_sent,
            messages_delivered=result.metrics.messages_delivered,
            messages_failed=result.metrics.messages_failed,
            delivery_ratio=result.metrics.delivery_ratio,
            retransmissions=result.metrics.retransmissions,
            modeled_latency_seconds=result.metrics.modeled_latency_seconds,
        )

    if name == "random_packet_loss":
        result = run_packet_loss_scenario(
            loss_probability=0.25,
            message_count=20,
            max_retries=2,
            seed=seed,
        )
        return ScenarioReport(
            scenario_name=name,
            seed=seed,
            parameters={"loss_probability": 0.25, "message_count": 20, "max_retries": 2},
            messages_sent=result.metrics.messages_sent,
            messages_delivered=result.metrics.messages_delivered,
            messages_failed=result.metrics.messages_failed,
            delivery_ratio=result.metrics.delivery_ratio,
            retransmissions=result.metrics.retransmissions,
            modeled_latency_seconds=result.metrics.modeled_latency_seconds,
        )

    failure_outcome = run_node_failure_scenario(
        pre_failure_messages=5,
        post_failure_messages=5,
        max_retries=2,
        loss_probability=0.0,
        seed=seed,
    )
    total_sent = failure_outcome.total_messages_sent
    total_delivered = failure_outcome.total_messages_delivered
    total_failed = (
        failure_outcome.pre_failure.metrics.messages_failed
        + failure_outcome.post_failure.metrics.messages_failed
    )
    total_retransmissions = (
        failure_outcome.pre_failure.metrics.retransmissions
        + failure_outcome.post_failure.metrics.retransmissions
    )
    total_latency = (
        failure_outcome.pre_failure.metrics.modeled_latency_seconds
        + failure_outcome.post_failure.metrics.modeled_latency_seconds
    )
    return ScenarioReport(
        scenario_name=name,
        seed=seed,
        parameters={
            "failed_node_id": failure_outcome.failed_node_id,
            "route_recovered": failure_outcome.route_recovered,
            "pre_failure_messages": 5,
            "post_failure_messages": 5,
        },
        messages_sent=total_sent,
        messages_delivered=total_delivered,
        messages_failed=total_failed,
        delivery_ratio=failure_outcome.overall_delivery_ratio,
        retransmissions=total_retransmissions,
        modeled_latency_seconds=total_latency,
    )


def export_scenario_reports(reports: Sequence[ScenarioReport], output_path: str | Path) -> Path:
    """Write a sequence of ScenarioReport objects to a JSON file."""
    if not reports:
        raise ValueError("reports must not be empty")
    for report in reports:
        if not isinstance(report, ScenarioReport):
            raise TypeError("all items in reports must be ScenarioReport instances")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"scenarios": [report.to_dict() for report in reports]}
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
