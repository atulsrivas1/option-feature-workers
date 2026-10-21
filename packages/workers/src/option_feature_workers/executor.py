"""One active whole-request owner; no plugins, callbacks or hidden parallelism."""
from dataclasses import asdict
from hashlib import sha256
import json
import threading
import unicodedata

from option_feature_contracts import (
    ContractValidationError, Request, Snapshot, content_digest,
    validate_request, validate_results, validate_snapshot,
)
from option_feature_io import (
    CommitReceipt, Publication, ResultSink, encode_request, encode_results,
    encode_snapshot,
)

from .types import (
    AdmissionError, CancellationToken, Cohort, ExecutionConfig, ExecutionError,
    PublicationError, ReplayItem, ResourceAdmission, RunReceipt, WorkerError,
)
from .verification import require_verified_cohort

_OWNER = threading.Lock()


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def cohort_digest(cohort: Cohort) -> str:
    """Identity only; this function does not verify an installation."""
    return sha256(b"option-cohort1\n" + _json(asdict(cohort))).hexdigest()


def _configuration(execution: ExecutionConfig, mode: str) -> None:
    if type(execution) is not ExecutionConfig or execution.mode != mode:
        raise AdmissionError("invalid_execution", "Wrong execution record or mode")
    for field in ("max_workers", "max_inflight", "memory_budget_bytes",
                  "logical_task_bytes", "io_slots", "backend_threads"):
        value = getattr(execution, field)
        if type(value) is not int or value <= 0:
            raise AdmissionError("invalid_execution", f"{field} must be a positive int")
    if (execution.max_workers, execution.max_inflight, execution.io_slots,
            execution.backend_threads) != (1, 1, 1, 1):
        raise AdmissionError("unsupported_execution", "Only the sequential one-thread profile is admitted")
    if execution.logical_task_bytes > execution.memory_budget_bytes:
        raise AdmissionError("resource_budget", "Logical task reservation exceeds total budget")


def _run_key(run_key: str) -> None:
    if (type(run_key) is not str or not run_key or len(run_key) > 256
            or any(unicodedata.category(c) == "Cc" for c in run_key)):
        raise AdmissionError("invalid_run_key", "run_key must be a nonempty bounded identifier")
    try:
        encoded = run_key.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AdmissionError("invalid_run_key", "run_key must be valid Unicode") from exc
    if len(encoded) > 1024:
        raise AdmissionError("invalid_run_key", "run_key exceeds its byte limit")


def inspect_resources(snapshot: Snapshot, request: Request,
                      execution: ExecutionConfig) -> ResourceAdmission:
    """Validate actual source records and expose reproducible logical accounting."""
    _configuration(execution, execution.mode if type(execution) is ExecutionConfig else "batch")
    if execution.mode not in ("batch", "replay"):
        raise AdmissionError("invalid_execution", "Unknown execution mode")
    validate_request(request)
    validate_snapshot(snapshot, request.limits)
    population_rows = int("chain.activity" in request.output_ids)
    rows = len(request.contract_ids) * (len(request.output_ids) - population_rows) + population_rows
    if rows > request.limits.max_result_rows:
        raise AdmissionError("admission_limit_exceeded", "Predicted results exceed row limit")
    snapshot_bytes = len(encode_snapshot(snapshot))
    request_bytes = len(encode_request(request))
    if max(snapshot_bytes, request_bytes) > request.limits.max_wire_bytes:
        raise AdmissionError("admission_limit_exceeded", "Canonical wire exceeds request byte limit")
    estimate = max(1048576, 4 * (snapshot_bytes + request_bytes) + 4096 * rows)
    if estimate > execution.logical_task_bytes:
        raise AdmissionError("resource_budget", "Declared reservation is smaller than the actual logical estimate")
    return ResourceAdmission(snapshot_bytes, request_bytes, rows, estimate,
                             execution.logical_task_bytes)


def _cancelled(cancel: CancellationToken, work: str | None = None) -> bool:
    try:
        value = cancel.is_cancelled()
    except Exception as exc:
        raise ExecutionError("cancellation_protocol", "Cancellation check failed", work) from exc
    if type(value) is not bool:
        raise ExecutionError("cancellation_protocol", "Cancellation must return bool", work)
    return value


def _identity(snapshot: Snapshot, request: Request, execution: ExecutionConfig,
              cohort: Cohort) -> tuple[str, str, str, str]:
    verified = require_verified_cohort(cohort)
    snapshot_hash = content_digest("snapshot", snapshot, request.limits)
    request_hash = content_digest("request", request, request.limits)
    cohort_hash = cohort_digest(cohort)
    payload = {"snapshot_sha256": snapshot_hash, "request_sha256": request_hash,
               "execution": asdict(execution), "cohort_sha256": cohort_hash,
               "worker_implementation_sha256": verified.worker_wheel_sha256}
    work = sha256(b"option-work1\n" + _json(payload)).hexdigest()
    return work, snapshot_hash, request_hash, cohort_hash


def _publish(sink: ResultSink, publication: Publication) -> CommitReceipt:
    expected_hash = content_digest("results", publication.results)
    try:
        receipt = sink.commit(publication)
    except Exception as original:
        # An exception can arrive after an atomic commit. Recovery must prove
        # the full expected publication, including bindings, by actual readback.
        try:
            recovered = sink.read(publication.run_key)
        except Exception as recovery:
            raise PublicationError("recovery_failed", "Publication failed and readback could not establish visibility",
                                   publication.work_sha256) from recovery
        if recovered != publication:
            raise PublicationError("publication_failed", "No identical committed publication was recovered",
                                   publication.work_sha256) from original
        receipt = CommitReceipt(publication.run_key, publication.work_sha256,
                                expected_hash, len(publication.results),
                                "already_committed", True)
    if (type(receipt) is not CommitReceipt or receipt.run_key != publication.run_key
            or receipt.work_sha256 != publication.work_sha256
            or receipt.results_sha256 != expected_hash
            or type(receipt.result_count) is not int
            or receipt.result_count != len(publication.results)
            or receipt.outcome not in ("committed", "already_committed")
            or receipt.readback_verified is not True):
        raise PublicationError("invalid_commit_receipt", "Sink returned an inconsistent receipt", publication.work_sha256)
    try:
        actual = sink.read(publication.run_key)
    except Exception as exc:
        raise PublicationError("readback_failed", "Commit visibility could not be verified", publication.work_sha256) from exc
    if actual != publication:
        raise PublicationError("readback_mismatch", "Full stored publication differs from expected content", publication.work_sha256)
    return receipt


def _execute(snapshot: Snapshot, request: Request, execution: ExecutionConfig,
             cohort: Cohort, run_key: str, sink: ResultSink | None,
             cancel: CancellationToken) -> RunReceipt:
    _run_key(run_key)
    require_verified_cohort(cohort)
    inspect_resources(snapshot, request, execution)
    work, snapshot_hash, request_hash, cohort_hash = _identity(snapshot, request, execution, cohort)
    if _cancelled(cancel, work):
        return RunReceipt(run_key, work, "cancelled", (), None, True)
    try:
        from option_features import evaluate
        results = evaluate(snapshot, request)
    except ContractValidationError as exc:
        exc.add_note("Worker work_sha256=" + work)
        raise
    except WorkerError:
        raise
    except Exception as exc:
        raise ExecutionError("evaluation_failed", "Pure evaluation failed", work) from exc
    if _cancelled(cancel, work):
        return RunReceipt(run_key, work, "cancelled", (), None, True)
    try:
        validate_results(results, request.limits)
    except ContractValidationError as exc:
        exc.add_note("Worker work_sha256=" + work)
        raise
    if not results or len(results) > request.limits.max_result_rows:
        raise ExecutionError("invalid_results", "Unexpected result cardinality", work)
    expected_pairs = tuple((contract_id, output_id) for contract_id in request.contract_ids
                           for output_id in request.output_ids if output_id != "chain.activity")
    expected_pairs += tuple((None, output_id) for output_id in request.output_ids if output_id == "chain.activity")
    if tuple((row.contract_id, row.output_id) for row in results) != expected_pairs:
        raise ExecutionError("invalid_results", "Evaluator ordering or selected outputs differ from request", work)
    if any(row.config_sha256 != request_hash or row.snapshot_sha256 != snapshot_hash for row in results):
        raise ExecutionError("invalid_results", "Evaluator content identity differs from admitted inputs", work)
    if len(encode_results(results)) > request.limits.max_wire_bytes:
        raise ExecutionError("admission_limit_exceeded", "Results exceed admitted wire limit", work)
    if _cancelled(cancel, work):
        return RunReceipt(run_key, work, "cancelled", (), None, True)
    if sink is None:
        return RunReceipt(run_key, work, "computed", results, None, False)
    publication = Publication(run_key, work, request_hash, snapshot_hash, cohort_hash,
                              results, tuple(sorted(snapshot.bindings, key=lambda b: b.binding_id)))
    receipt = _publish(sink, publication)
    # Once committed, cancellation cannot turn visible output into cancellation.
    try:
        observed = _cancelled(cancel, work)
    except ExecutionError as exc:
        raise PublicationError("committed_cancellation_check_failed",
                               "Generation is committed and readback verified; the subsequent cancellation check failed",
                               work) from exc
    return RunReceipt(run_key, work, receipt.outcome, results, receipt, observed)


def execute(snapshot: Snapshot, request: Request, execution: ExecutionConfig,
            cohort: Cohort, run_key: str, sink: ResultSink | None,
            cancel: CancellationToken) -> RunReceipt:
    _configuration(execution, "batch")
    if not _OWNER.acquire(blocking=False):
        raise AdmissionError("worker_busy", "Another whole-request owner is active")
    try:
        return _execute(snapshot, request, execution, cohort, run_key, sink, cancel)
    finally:
        _OWNER.release()


def replay(items: tuple[ReplayItem, ...], execution: ExecutionConfig,
           cohort: Cohort, sink: ResultSink | None,
           cancel: CancellationToken) -> tuple[RunReceipt, ...]:
    _configuration(execution, "replay")
    if type(items) is not tuple:
        raise AdmissionError("invalid_replay", "Replay requires a tuple of independent snapshots")
    if not _OWNER.acquire(blocking=False):
        raise AdmissionError("worker_busy", "Another whole-request owner is active")
    try:
        receipts = []
        for item in items:
            if type(item) is not ReplayItem:
                raise AdmissionError("invalid_replay", "Replay item has the wrong type")
            receipt = _execute(item.snapshot, item.request, execution, cohort, item.run_key, sink, cancel)
            receipts.append(receipt)
            if receipt.outcome == "cancelled" or receipt.cancellation_observed:
                break
        return tuple(receipts)
    finally:
        _OWNER.release()
