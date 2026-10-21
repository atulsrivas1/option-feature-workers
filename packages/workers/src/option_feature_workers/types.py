"""Frozen R25 orchestration records. Numerical records belong to contracts."""
from dataclasses import dataclass
from typing import Literal, Protocol

from option_feature_contracts import Request, Result, Snapshot
from option_feature_io import CommitReceipt


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    mode: Literal["batch", "replay"]
    max_workers: int
    max_inflight: int
    memory_budget_bytes: int
    logical_task_bytes: int
    io_slots: int
    backend_threads: Literal[1]


@dataclass(frozen=True, slots=True)
class Artifact:
    distribution: str
    version: str
    source_commit: str
    wheel_sha256: str
    role: Literal["contracts", "calculations", "io", "workers", "dependency"]


@dataclass(frozen=True, slots=True)
class Cohort:
    cohort_version: Literal["option-cohort1"]
    python_version: str
    platform_id: str
    artifacts: tuple[Artifact, ...]


@dataclass(frozen=True, slots=True)
class ReplayItem:
    snapshot: Snapshot
    request: Request
    run_key: str


@dataclass(frozen=True, slots=True)
class RunReceipt:
    run_key: str
    work_sha256: str
    outcome: Literal["computed", "committed", "already_committed", "cancelled"]
    results: tuple[Result, ...]
    commit_receipt: CommitReceipt | None
    cancellation_observed: bool


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ResourceAdmission:
    snapshot_wire_bytes: int
    request_wire_bytes: int
    predicted_result_rows: int
    estimated_logical_bytes: int
    reserved_logical_bytes: int
    unit: Literal["bytes"] = "bytes"
    limitation: str = "logical reservation; not an RSS or native-allocation bound"


class WorkerError(RuntimeError):
    """A failed run, never a successful receipt."""

    def __init__(self, code: str, message: str, work_sha256: str | None = None):
        super().__init__(message)
        self.code = code
        self.work_sha256 = work_sha256


class AdmissionError(WorkerError):
    pass


class CohortVerificationError(WorkerError):
    pass


class ExecutionError(WorkerError):
    pass


class PublicationError(WorkerError):
    pass
