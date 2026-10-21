"""Closed frozen R26 orchestration records; no calculation or storage behavior."""
from dataclasses import dataclass
from typing import Literal, Protocol
from option_flow_contracts import FlowResult, FlowCheckpoint
from option_flow_io import FlowCommitReceipt

@dataclass(frozen=True, slots=True)
class FlowExecutionConfig:
    mode: Literal["batch", "chronological_cut_replay", "checkpoint_restore"]
    max_workers: int
    max_inflight: int
    io_slots: int
    backend_threads: int
    memory_budget_bytes: int
    logical_task_bytes: int

@dataclass(frozen=True, slots=True)
class FlowArtifact:
    distribution: str
    version: str
    source_commit: str
    wheel_sha256: str
    role: Literal["contracts", "calculations", "io", "workers", "dependency"]

@dataclass(frozen=True, slots=True)
class FlowCohort:
    cohort_version: Literal["option-flow-cohort1"]
    python_version: str
    platform_id: str
    artifacts: tuple[FlowArtifact, ...]

@dataclass(frozen=True, slots=True)
class FlowAdmission:
    snapshot_wire_bytes: int
    request_wire_bytes: int
    checkpoint_wire_bytes: int
    predicted_result_rows: int
    estimated_logical_bytes: int
    reserved_logical_bytes: int
    limitation: str = "logical reservation; not an RSS or native-allocation bound"

@dataclass(frozen=True, slots=True)
class FlowRunReceipt:
    run_key: str
    work_sha256: str
    outcome: Literal["computed", "committed", "already_committed", "cancelled"]
    results: tuple[FlowResult, ...]
    output_checkpoint: FlowCheckpoint | None
    commit_receipt: FlowCommitReceipt | None
    cancellation_observed: bool

class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...

class FlowWorkerError(RuntimeError):
    def __init__(self, code: str, message: str, *, cause_code: str | None = None,
                 cause_path: str | None = None):
        super().__init__(message)
        self.code = code
        self.cause_code = cause_code
        self.cause_path = cause_path

class FlowCohortVerificationError(FlowWorkerError):
    pass
