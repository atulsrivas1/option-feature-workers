"""Serialized whole-ledger execution with immutable publication boundaries."""
from dataclasses import asdict, fields, is_dataclass
from hashlib import sha256
import json
import re
import threading

from option_flow_contracts import (
    FlowValidationError, FlowSnapshot, FlowRequest, FlowCheckpoint,
    flow_canonical_bytes, flow_record_digest, flow_validate_snapshot,
    flow_validate_request, flow_validate_results,
)
from option_flow_io import (
    FlowPublication, FlowCommitReceipt, encode_flow_snapshot,
    encode_flow_request, encode_flow_checkpoint, encode_flow_results,
    encode_flow_publication,
)
from .types import FlowAdmission, FlowCohort, FlowExecutionConfig, FlowRunReceipt, FlowWorkerError
from .verification import require_verified_flow_cohort

_OWNER = threading.Lock()
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_CLUSTER = frozenset(("execution.cluster_premium", "execution.cluster_trade_count",
                      "execution.cluster_contracts", "execution.cluster_span_ns",
                      "execution.cluster_venue_count"))


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def flow_cohort_digest(cohort: FlowCohort) -> str:
    """Hash identity only; verification remains a separate mandatory operation."""
    return sha256(b"option-flow-cohort1\n" + _json(asdict(cohort))).hexdigest()


def _configuration(config, mode):
    if type(config) is not FlowExecutionConfig or config.mode != mode:
        raise FlowWorkerError("unsupported_mode", "Wrong execution mode/configuration")
    if mode not in ("batch", "chronological_cut_replay", "checkpoint_restore"):
        raise FlowWorkerError("unsupported_mode", "Unsupported execution mode")
    for field in fields(config):
        if field.name == "mode":
            continue
        value = getattr(config, field.name)
        if type(value) is not int or value <= 0:
            raise FlowWorkerError("unsupported_resources", "Resources must be exact positive integers")
    if (config.max_workers, config.max_inflight, config.io_slots, config.backend_threads) != (1, 1, 1, 1):
        raise FlowWorkerError("unsupported_resources", "Only one worker/inflight/I/O/native thread is admitted")
    if config.logical_task_bytes < 268435456 or config.logical_task_bytes > config.memory_budget_bytes:
        raise FlowWorkerError("resource_limit", "Logical reservation outside the admitted memory budget")


def _key(run_key):
    if type(run_key) is not str or _IDENTIFIER.fullmatch(run_key) is None:
        raise FlowWorkerError("input_invalid", "run_key must be a closed ASCII identifier")


def _cancelled(token):
    if token is None:
        return False
    try:
        value = token.is_cancelled()
    except Exception as exc:
        raise FlowWorkerError("execution_failed", "Cancellation protocol failed") from exc
    if type(value) is not bool:
        raise FlowWorkerError("input_invalid", "Cancellation must return an exact bool")
    return value


def _record_count(value):
    if is_dataclass(value):
        return 1 + sum(_record_count(getattr(value, field.name)) for field in fields(value))
    if type(value) is tuple:
        return sum(_record_count(item) for item in value)
    return 0


def inspect_flow_resources(snapshot, request, config, checkpoint=None):
    """Expose deterministic logical accounting; this does not enforce RSS."""
    _configuration(config, config.mode if type(config) is FlowExecutionConfig else "batch")
    flow_validate_request(request)
    flow_validate_snapshot(snapshot, request.limits)
    flow_validate_request(request, snapshot)
    snapshot_bytes = len(encode_flow_snapshot(snapshot))
    request_bytes = len(encode_flow_request(request))
    checkpoint_bytes = 0 if checkpoint is None else len(encode_flow_checkpoint(checkpoint))
    if max(snapshot_bytes, request_bytes, checkpoint_bytes) > request.limits.max_wire_bytes:
        raise FlowWorkerError("resource_limit", "Wire envelope exceeds request bound")
    scalar_count = len(set(request.output_ids) - _CLUSTER)
    clusters = len(set(request.output_ids) & _CLUSTER)
    groups = {group.group_id: group for group in snapshot.groups}
    predicted = len(request.group_ids) * scalar_count
    for group_id in request.group_ids:
        group = groups[group_id]
        roots = {item.execution_id for item in snapshot.executions
                 if item.contract_id in group.contract_ids and item.kind == "new"
                 and request.window_start_ns <= item.event_ns < request.window_end_ns}
        predicted += clusters * max(1, len(roots))
    if predicted > request.limits.max_result_rows:
        raise FlowWorkerError("resource_limit", "Predicted row reservation exceeds limit")
    count = _record_count(snapshot) + _record_count(request)
    # Checkpoint history is the same retained identity in the merged snapshot;
    # encoded bytes are charged again, records only once.
    estimate = 4 * (snapshot_bytes + request_bytes + checkpoint_bytes) + 4096 * count + 2048 * predicted
    if estimate > config.logical_task_bytes:
        raise FlowWorkerError("resource_limit", "Logical estimate exceeds declared reservation")
    return FlowAdmission(snapshot_bytes, request_bytes, checkpoint_bytes, predicted,
                         estimate, config.logical_task_bytes)


def _identity(snapshot, request, cohort, checkpoint):
    snapshot_hash = flow_record_digest("flow_snapshot", snapshot)
    request_hash = flow_record_digest("flow_request", request)
    checkpoint_hash = None if checkpoint is None else flow_record_digest("flow_checkpoint", checkpoint)
    cohort_hash = flow_cohort_digest(cohort)
    work = sha256(b"option-flow-work1\n" + _json([
        snapshot_hash, request_hash, cohort_hash, checkpoint_hash])).hexdigest()
    return work, snapshot_hash, request_hash, cohort_hash, checkpoint_hash


def _checkpoint(snapshot, request):
    from option_flow_features import make_flow_checkpoint
    try:
        return make_flow_checkpoint(snapshot, request)
    except FlowValidationError as exc:
        if exc.code == "checkpoint_cut_mismatch":
            return None
        raise


def _merge_restore(checkpoint, suffix, request):
    # One pure implementation owns ancestor/identity/cursor semantics. It returns
    # the actual retained ledger, which workers bind in work/publication identity.
    from option_flow_features.engine import merge_flow_history
    return merge_flow_history(checkpoint, suffix, request)


def _translate(exc):
    if isinstance(exc, FlowWorkerError):
        return exc
    if isinstance(exc, FlowValidationError):
        code = "resource_limit" if exc.code == "resource_limit" else "input_invalid"
        return FlowWorkerError(code, "Flow validation failed", cause_code=exc.code,
                               cause_path=exc.path)
    mapping = {"PublicationConflict": "publication_conflict", "StorageIntegrityError": "storage_integrity",
               "StorageSchemaError": "storage_schema"}
    return FlowWorkerError(mapping.get(type(exc).__name__, "execution_failed"), "Flow execution failed")


def _run(snapshot, request, *, run_key, config, verified_cohort, sink, cancellation, checkpoint=None):
    require_verified_flow_cohort(verified_cohort)
    identity = _identity(snapshot, request, verified_cohort, checkpoint)
    work, snapshot_hash, request_hash, cohort_hash, input_hash = identity
    cancelled = lambda: FlowRunReceipt(run_key, work, "cancelled", (), None, None, True)
    if _cancelled(cancellation):
        return cancelled()
    inspect_flow_resources(snapshot, request, config, checkpoint)
    # Cooperative record traversal checks precede reducer entry. The evaluator is
    # pure: no cancellation object or I/O callback enters calculation packages.
    for family in (snapshot.bindings, snapshot.references, snapshot.executions, snapshot.quotes,
                   snapshot.groups, snapshot.populations, snapshot.context_certificates, snapshot.baselines):
        for unused_record in family:
            if _cancelled(cancellation):
                return cancelled()
    if _cancelled(cancellation):
        return cancelled()
    from option_flow_features.engine import _evaluate_steps
    steps = _evaluate_steps(snapshot, request, input_checkpoint_sha256=input_hash)
    try:
        while True:
            if _cancelled(cancellation):
                return cancelled()
            try:
                next(steps)
            except StopIteration as finished:
                results = finished.value
                break
    finally:
        steps.close()
    flow_validate_results(results, request)
    for result in results:
        if _cancelled(cancellation):
            return cancelled()
        if (result.request_sha256, result.snapshot_sha256, result.checkpoint_sha256) != (
                request_hash, snapshot_hash, input_hash):
            raise FlowWorkerError("execution_failed", "Evaluator returned mismatched invocation identity")
    output_checkpoint = _checkpoint(snapshot, request)
    encode_flow_results(results)
    if _cancelled(cancellation):
        return cancelled()
    require_verified_flow_cohort(verified_cohort)
    if _cancelled(cancellation):
        return cancelled()
    if sink is None:
        return FlowRunReceipt(run_key, work, "computed", results, output_checkpoint, None, False)
    publication = FlowPublication("option-flow-generation1", run_key, work, request,
                                  request_hash, snapshot_hash, cohort_hash, input_hash,
                                  results, tuple(sorted(snapshot.bindings, key=lambda item: item.binding_id)),
                                  output_checkpoint)
    encode_flow_publication(publication)
    if _cancelled(cancellation):
        return cancelled()
    require_verified_flow_cohort(verified_cohort)
    if _cancelled(cancellation):
        return cancelled()
    # No cancellation abort is allowed after this transaction boundary.
    receipt = sink.publish(publication)
    if type(receipt) is not FlowCommitReceipt:
        raise FlowWorkerError("storage_integrity", "Sink returned wrong receipt type")
    publication_hash = flow_record_digest("flow_publication", publication)
    results_hash = flow_record_digest("flow_results", results)
    output_hash = None if output_checkpoint is None else flow_record_digest("flow_checkpoint", output_checkpoint)
    if (receipt.run_key, receipt.work_sha256, receipt.publication_sha256,
            receipt.results_sha256, receipt.output_checkpoint_sha256, receipt.result_count,
            receipt.verified_readback) != (
                run_key, work, publication_hash, results_hash, output_hash, len(results), True
            ) or receipt.outcome not in ("committed", "already_committed"):
        raise FlowWorkerError("storage_integrity", "Sink receipt disagrees with complete publication")
    stored = sink.read(run_key)
    if stored is None or flow_canonical_bytes(stored) != flow_canonical_bytes(publication):
        raise FlowWorkerError("storage_integrity", "Complete publication readback differs")
    return FlowRunReceipt(run_key, work, receipt.outcome, results, output_checkpoint, receipt,
                          _cancelled(cancellation))


def _owned(action):
    if not _OWNER.acquire(blocking=False):
        raise FlowWorkerError("resource_busy", "Another flow invocation owns execution")
    try:
        return action()
    except Exception as exc:
        translated = _translate(exc)
        if translated is exc:
            raise
        raise translated from exc
    finally:
        _OWNER.release()


def execute_flow(snapshot, request, *, run_key, config, verified_cohort, sink=None, cancellation=None):
    _configuration(config, "batch")
    _key(run_key)
    return _owned(lambda: _run(snapshot, request, run_key=run_key, config=config,
                              verified_cohort=verified_cohort, sink=sink, cancellation=cancellation))


def execute_flow_replay(snapshot, requests, *, run_keys, config, verified_cohort, sink=None, cancellation=None):
    _configuration(config, "chronological_cut_replay")
    if (type(requests) is not tuple or type(run_keys) is not tuple or not requests
            or len(requests) > 128 or len(requests) != len(run_keys)):
        raise FlowWorkerError("input_invalid", "Replay requires bounded matching unique cuts/run keys")
    for key in run_keys:
        _key(key)
    if len(set(run_keys)) != len(run_keys):
        raise FlowWorkerError("input_invalid", "Replay run keys must be unique")
    def validate_cuts():
        # Validate every cut/chronological relation before first publication.
        prior = None
        for request in requests:
            flow_validate_request(request)
            if len(requests) > request.limits.max_replay_cuts:
                raise FlowWorkerError("resource_limit", "Too many replay cuts")
            if prior is not None:
                old = {item.stream_id: item.max_position for item in prior.cut_cursors}
                new = {item.stream_id: item.max_position for item in request.cut_cursors}
                if (request.group_ids != prior.group_ids or request.output_ids != prior.output_ids
                        or request.policy != prior.policy or request.window_start_ns != prior.window_start_ns
                        or request.window_end_ns < prior.window_end_ns
                        or request.knowledge_cutoff_ns < prior.knowledge_cutoff_ns
                        or set(old) != set(new) or any(new[key] < old[key] for key in old)):
                    raise FlowWorkerError("input_invalid", "Replay cuts must be chronological over one immutable ledger")
            prior = request
    def action():
        validate_cuts()
        receipts = []
        for request, run_key in zip(requests, run_keys):
            if receipts and _cancelled(cancellation):
                break
            receipt = _run(snapshot, request, run_key=run_key, config=config,
                           verified_cohort=verified_cohort, sink=sink, cancellation=cancellation)
            receipts.append(receipt)
            if receipt.outcome == "cancelled":
                break
        return tuple(receipts)
    return _owned(action)


def execute_flow_restore(checkpoint, suffix, request, *, run_key, config, verified_cohort, sink=None, cancellation=None):
    _configuration(config, "checkpoint_restore")
    _key(run_key)
    def action():
        require_verified_flow_cohort(verified_cohort)
        merged = _merge_restore(checkpoint, suffix, request)
        return _run(merged, request, run_key=run_key, config=config,
                    verified_cohort=verified_cohort, sink=sink, cancellation=cancellation,
                    checkpoint=checkpoint)
    return _owned(action)
