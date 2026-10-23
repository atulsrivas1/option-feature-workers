"""Worker entry points for option-flow-variants1: execute, restore and bounded replay.

The caller supplies an externally verified cohort (a Cohort record) and, when it
needs the installed token rechecked before publication, a `reverify` callable
returning the currently verified Cohort. Verification of installed artifacts is
outside this module. No service, queue or background thread is involved.
"""
from option_feature_contracts.variants1.canonical import VariantValidationError, canonical_json, cohort_digest
from option_feature_contracts.variants1.schema import validate_scalars, validate_shape
from option_features.variants1 import admission as _admission

from .errors import VariantWorkerError, input_invalid
from .run import run_batch, run_restore
from .storage import (
    PublicationConflict, StorageIntegrityError, StorageSchemaError, commit_receipt, envelope,
)

MAX_REPLAY = 128
_RESOURCE_FIELDS = ("max_workers", "max_inflight", "io_slots", "backend_threads")
_MODES = ("batch", "chronological_cut_replay", "checkpoint_restore")


def _check_config(config, mode):
    try:
        validate_shape(config, "ExecutionConfig", "/config")
    except VariantValidationError as exc:
        raise input_invalid(exc) from exc
    if config["mode"] not in _MODES or config["mode"] != mode:
        raise VariantWorkerError("unsupported_mode")
    for key in _RESOURCE_FIELDS:
        if config[key] != 1:
            raise VariantWorkerError("unsupported_resources")
    if config["logical_task_bytes"] < 268435456 or config["logical_task_bytes"] > config["memory_budget_bytes"]:
        raise VariantWorkerError("resource_limit")
    try:
        validate_scalars(config, "ExecutionConfig", "/config")
    except VariantValidationError as exc:
        raise input_invalid(exc) from exc


def _check_admission(config, request, admission):
    """Plain decoded admission is admitted only when it matches the expected hash and receipts."""
    expected = config["producer_admission_sha256"]
    actual = None if admission is None else _admission.admission_hash(admission)
    if expected != actual or request.get("producer_admission_sha256") != actual:
        raise VariantWorkerError("cohort_unverified")
    if admission is not None:
        receipts = set(config["producer_qualification_receipt_sha256s"])
        for entry in admission["qualified_inputs"]:
            if entry["qualification_receipt_sha256"] not in receipts:
                raise VariantWorkerError("cohort_unverified")


def _cancelled(cancellation):
    return cancellation is not None and bool(cancellation.is_cancelled())


def _receipt(computed, outcome, commit, observed):
    return {
        "run_key": computed["run_key"], "work_sha256": computed["work_sha256"], "outcome": outcome,
        "results": computed["results"], "output_checkpoint": computed["output_checkpoint"],
        "commit_receipt": commit, "cancellation_observed": observed,
    }


def _publish(sink, publication):
    """Commit, recovering an uncertain acknowledgement by identical verified readback."""
    try:
        return sink.publish(publication)
    except (PublicationConflict, StorageIntegrityError, StorageSchemaError):
        raise
    except Exception as original:
        stored = sink.read(publication["run_key"])
        if stored is None:
            raise VariantWorkerError("execution_failed") from original
        if canonical_json(stored) != canonical_json(publication):
            raise PublicationConflict("different publication under the run key") from original
        return commit_receipt(publication, "committed")


def execute_variants(snapshot, request, *, run_key, config, verified_cohort, verified_producer_admission=None,
                     sink=None, cancellation=None, reverify=None, input_checkpoint=None, suffix=None):
    """Run one batch or checkpoint-restore invocation and optionally commit it.

    Returns a RunReceipt record. Without a sink the outcome is computed. A
    cancellation observed before publication returns cancelled with nothing
    committed; once the transaction has begun the actual commit is reported.
    """
    mode = config.get("mode") if isinstance(config, dict) else None
    _check_config(config, "checkpoint_restore" if mode == "checkpoint_restore" else "batch")
    if verified_cohort is None:
        raise VariantWorkerError("cohort_unverified")
    _check_admission(config, request, verified_producer_admission)
    if config["mode"] == "checkpoint_restore":
        if input_checkpoint is None or suffix is None:
            raise VariantWorkerError("input_invalid")
        computed = run_restore(input_checkpoint, suffix, request, verified_cohort, run_key,
                               producer_admission=verified_producer_admission)
    else:
        computed = run_batch(snapshot, request, verified_cohort, run_key,
                             producer_admission=verified_producer_admission)
    if sink is None:
        return _receipt(computed, "computed", None, False)
    if _cancelled(cancellation):
        return {"run_key": run_key, "work_sha256": computed["work_sha256"], "outcome": "cancelled",
                "results": None, "output_checkpoint": None, "commit_receipt": None,
                "cancellation_observed": True}
    if reverify is not None and cohort_digest(reverify()) != cohort_digest(verified_cohort):
        raise VariantWorkerError("cohort_changed")
    commit = _publish(sink, computed["publication"])
    return _receipt(computed, commit["outcome"], commit, _cancelled(cancellation))


def replay_variants(snapshot, requests, run_keys, *, config, verified_cohort, verified_producer_admission=None,
                    sink=None, cancellation=None, reverify=None):
    """Chronological cut replay: each explicit Request is an independent batch run over the Snapshot.

    Runs sequentially; a failure stops the replay and leaves every earlier commit in place;
    the raised error carries the earlier receipts as `completed`.
    """
    _check_config(config, "chronological_cut_replay")
    if len(requests) != len(run_keys) or not requests or len(requests) > MAX_REPLAY:
        raise VariantWorkerError("input_invalid")
    step_config = dict(config, mode="batch")
    receipts = []
    for request, run_key in zip(requests, run_keys):
        try:
            receipts.append(execute_variants(
                snapshot, request, run_key=run_key, config=step_config, verified_cohort=verified_cohort,
                verified_producer_admission=verified_producer_admission, sink=sink, cancellation=cancellation,
                reverify=reverify))
        except VariantWorkerError as exc:
            exc.completed = receipts  # receipts of the steps committed before the failure
            raise
        if receipts[-1]["outcome"] == "cancelled":
            break
    return receipts


def run_envelope(receipt):
    """Canonical envelope text of a RunReceipt."""
    return envelope("variant_RunReceipt", receipt)
