"""Run translation for option-flow-variants1 (batch and checkpoint restore).

Returns RunReceipt-shaped dicts with outcome "computed". Storage, commit and
cancellation are outside this module; no sink is ever called here.
"""
from option_feature_contracts.variants1.canonical import VariantValidationError, cohort_digest, record_digest
from option_features.variants1.evaluate import build_publication, evaluate_variants

from .checkpoint import cut_history, make_checkpoint, validate_restore
from .errors import VariantWorkerError, input_invalid


def _compute(snapshot, request, cohort, run_key, cohort_verified, input_checkpoint, producer_admission):
    if not cohort_verified:
        raise VariantWorkerError("cohort_unverified")
    cohort_sha = cohort_digest(cohort)
    input_hash = None if input_checkpoint is None else record_digest("variant_Checkpoint", input_checkpoint)
    try:
        results = evaluate_variants(snapshot, request, cohort_sha256=cohort_sha,
                                    input_checkpoint_sha256=input_hash,
                                    producer_admission=producer_admission)
        out_cp = make_checkpoint(cut_history(snapshot, request), request, cohort, producer_admission)
        pub = build_publication(snapshot, request, results, run_key=run_key, cohort=cohort,
                                cohort_sha256=cohort_sha, producer_admission=producer_admission,
                                input_checkpoint_sha256=input_hash, output_checkpoint=out_cp)
    except VariantValidationError as exc:
        raise input_invalid(exc) from exc
    return {
        "run_key": run_key,
        "work_sha256": pub["work_sha256"],
        "outcome": "computed",
        "results": results,
        "output_checkpoint": out_cp,
        "commit_receipt": None,
        "cancellation_observed": False,
        "publication": pub,
    }


def run_batch(snapshot, request, cohort, run_key, *, cohort_verified=True, producer_admission=None):
    """Batch mode: full Snapshot and Request, no input checkpoint."""
    return _compute(snapshot, request, cohort, run_key, cohort_verified, None, producer_admission)


def run_restore(checkpoint, suffix, request, cohort, run_key, *, cohort_verified=True,
                producer_admission=None):
    """Checkpoint restore: CP0-CP3 validation and immutable merge, then evaluation.

    Validation failures raise VariantWorkerError('input_invalid') with the typed
    cause and do not evaluate, publish or advance any checkpoint.
    """
    if not cohort_verified:
        raise VariantWorkerError("cohort_unverified")
    try:
        merged = validate_restore(checkpoint, request, suffix, cohort_digest(cohort), producer_admission)
    except VariantValidationError as exc:
        raise input_invalid(exc) from exc
    return _compute(merged, request, cohort, run_key, True, checkpoint, producer_admission)
