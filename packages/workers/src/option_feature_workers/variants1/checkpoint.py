"""Checkpoint construction and restore validation (CP0-CP3) for option-flow-variants1.

Pure functions over closed records. Errors use the typed VariantValidationError
from option_feature_contracts.variants1 so the worker can translate them.
"""
from option_feature_contracts.variants1.canonical import (
    FORMULA, SCHEMA_CHECKPOINT, VariantValidationError, canonical_json, cohort_digest, fail, record_digest,
)
from option_feature_contracts.variants1.schema import validate_scalars, validate_shape
from option_features.variants1 import admission as _admission
from option_features.variants1.context import Ctx

# Snapshot collections in declaration order, with their identity field.
COLLECTIONS = (
    ("bindings", "binding_id"), ("scopes", "scope_id"), ("definitions", "definition_id"),
    ("references", "reference_id"), ("executions", "revision_id"), ("quotes", "revision_id"),
    ("pairings", "pairing_id"), ("controls", "control_id"), ("supplied_premiums", "premium_id"),
    ("daily_observations", "observation_id"), ("baseline_slots", "slot_id"),
    ("bucket_policies", "policy_id"), ("session_frames", "frame_id"),
    ("activity_targets", "target_id"), ("bucket_certificates", "certificate_id"),
    ("daily_activity_certificates", "certificate_id"),
)


def cut_history(snapshot, request):
    """Causal history at the Request cut: stamped records beyond their stream cursor are dropped.

    Records whose stream has no cut cursor are kept unchanged.
    """
    cursors = {c["stream_id"]: c["position"] for c in request["cut_cursors"]}
    out = dict(snapshot)
    for name, _ in COLLECTIONS:
        kept = []
        for r in snapshot.get(name, []):
            st = r.get("stamp")
            if st is not None and st["stream_id"] in cursors and st["position"] > cursors[st["stream_id"]]:
                continue
            kept.append(r)
        out[name] = kept
    return out


def cut_complete(history, request):
    """True when the whole history lies inside the Request cut.

    Every stamped record sits at or below its stream cursor and is known by K,
    and the history cursors equal the Request cut cursors.
    """
    cursors = {c["stream_id"]: c["position"] for c in request["cut_cursors"]}
    if {c["stream_id"]: c["position"] for c in history.get("cursors", [])} != cursors:
        return False
    for name, _ in COLLECTIONS:
        for r in history.get(name, []):
            st = r.get("stamp")
            if st is None:
                continue
            if st["stream_id"] not in cursors or st["position"] > cursors[st["stream_id"]]:
                return False
            if st["known_at_ns"] > request["knowledge_K_ns"]:
                return False
    return True


def make_checkpoint(history, prior_request, cohort, producer_admission=None):
    """Output checkpoint for a completed run, or None unless the history is cut-complete."""
    if not cut_complete(history, prior_request):
        return None
    return {
        "schema_version": SCHEMA_CHECKPOINT,
        "history": history,
        "prior_request": prior_request,
        "history_sha256": record_digest("variant_Snapshot", history),
        "prior_request_sha256": record_digest("variant_Request", prior_request),
        "policy_sha256s": [record_digest("variant_Policy", p) for p in sorted(prior_request["policies"], key=lambda p: p["policy_id"])],
        "evaluator_cohort_sha256": cohort_digest(cohort),
        "producer_admission": producer_admission,
        "formula_version": FORMULA,
    }


def _admission_prefix_ok(prior, current):
    if prior is None:
        return True
    if current is None:
        return False
    a, b = prior["qualified_inputs"], current["qualified_inputs"]
    return len(b) >= len(a) and list(b[:len(a)]) == list(a)


def _retained_admission_digest_ok(prior_request, admission):
    stored = prior_request["producer_admission_sha256"]
    if admission is None:
        return stored is None
    return stored == _admission.admission_hash(admission)


def _remap(exc):
    """Re-root a library path from the batch locations to the embedded checkpoint locations."""
    path = exc.path
    for old, new in (("/snapshot", "/checkpoint/history"), ("/request", "/checkpoint/prior_request")):
        if path == old or path.startswith(old + "/"):
            path = new + path[len(old):]
            break
    return VariantValidationError(exc.code, path, exc.stage)


def _regression_after_temporal(history, suffix, request, checkpoint, producer_admission):
    """CP3 order: existing temporal rules (e.g. root A>K) precede cut-cursor regression.

    Runs admission over the unconflicted union of retained and suffix records and
    lets only the root A>K temporal_cut (at /request/knowledge_K_ns) through; anything else falls to the caller.
    """
    union = dict(history)
    for name, key in COLLECTIONS:
        seen = {}
        for r in list(history.get(name, [])) + list(suffix.get(name, [])):
            seen.setdefault(r[key], r)
        union[name] = [seen[k] for k in sorted(seen)]
    ctx = Ctx(union, request, checkpoint["evaluator_cohort_sha256"], producer_admission, None)
    try:
        _admission.stage5(ctx)
        _admission.stage6(ctx)
        _admission.stage7(ctx)
    except VariantValidationError as exc:
        if exc.code == "temporal_cut" and exc.path == "/request/knowledge_K_ns":
            raise


def validate_restore(checkpoint, request, suffix, cohort_sha256, producer_admission=None):
    """CP0-CP3 checks, then immutable merge. Returns the merged Snapshot.

    cohort_sha256 is the current evaluator cohort digest. Raises
    VariantValidationError with the first failing typed code and pointer.
    """
    # CP0: closed Checkpoint envelope shape and scalars.
    validate_shape(checkpoint, "Checkpoint", "/checkpoint")
    validate_scalars(checkpoint, "Checkpoint", "/checkpoint")
    history = checkpoint["history"]
    prior = checkpoint["prior_request"]
    # CP1a: stored history and prior Request identities, references and temporal admission.
    ctx = Ctx(history, prior, checkpoint["evaluator_cohort_sha256"], checkpoint["producer_admission"], None)
    try:
        _admission.stage5(ctx)
        _admission.stage6(ctx)
        _admission.stage7(ctx)
    except VariantValidationError as exc:
        raise _remap(exc) from None
    # CP1b: retained digests in declaration order.
    if checkpoint["history_sha256"] != record_digest("variant_Snapshot", history):
        fail("digest_mismatch", "/checkpoint/history_sha256", 1)
    if checkpoint["prior_request_sha256"] != record_digest("variant_Request", prior):
        fail("digest_mismatch", "/checkpoint/prior_request_sha256", 1)
    expected = [record_digest("variant_Policy", p) for p in sorted(prior["policies"], key=lambda p: p["policy_id"])]
    stored = checkpoint["policy_sha256s"]
    if len(stored) != len(expected):
        fail("digest_mismatch", "/checkpoint/policy_sha256s", 1)
    for i, h in enumerate(expected):
        if stored[i] != h:
            fail("digest_mismatch", "/checkpoint/policy_sha256s/%d" % i, 1)
    if not _retained_admission_digest_ok(prior, checkpoint["producer_admission"]):
        fail("digest_mismatch", "/checkpoint/prior_request/producer_admission_sha256", 1)
    # CP2: retained evaluator identity must match the current run.
    if checkpoint["evaluator_cohort_sha256"] != cohort_sha256:
        fail("checkpoint_cut_mismatch", "/checkpoint/evaluator_cohort_sha256", 2)
    # CP3: current Request and suffix shape, then admission extension, cut and merge.
    validate_shape(request, "Request", "/request")
    validate_shape(suffix, "Snapshot", "/snapshot")
    validate_scalars(request, "Request", "/request")
    validate_scalars(suffix, "Snapshot", "/snapshot")
    # CP3 first: a retained cut stream dropped from the current cut is a cut mismatch (index-free pointer).
    current_streams = {c["stream_id"] for c in request["cut_cursors"]}
    if any(c["stream_id"] not in current_streams for c in prior["cut_cursors"]):
        fail("checkpoint_cut_mismatch", "/request/cut_cursors", 3)
    if not _admission_prefix_ok(checkpoint["producer_admission"], producer_admission):
        fail("checkpoint_cut_mismatch", "/checkpoint/producer_admission", 3)
    # CP3 (1): current request knowledge may not regress.
    if request["knowledge_K_ns"] < prior["knowledge_K_ns"]:
        fail("checkpoint_cut_mismatch", "/request/knowledge_K_ns", 3)
    # CP3 (2): cut cursor positions may not regress, scanned in current index order.
    retained = {c["stream_id"]: c["position"] for c in prior["cut_cursors"]}
    for i, c in enumerate(request["cut_cursors"]):
        if c["stream_id"] in retained and c["position"] < retained[c["stream_id"]]:
            _regression_after_temporal(history, suffix, request, checkpoint, producer_admission)
            fail("checkpoint_cut_mismatch", "/request/cut_cursors/%d/position" % i, 3)
    # Root A>K temporal_cut also precedes the merge (merge is last in CP3).
    _regression_after_temporal(history, suffix, request, checkpoint, producer_admission)
    # CP3 (3): immutable merge. Byte-identical retained identities are reusable;
    # a changed record under a retained identity is an identity_conflict; a repeated
    # identity inside the suffix is rejected as batch uniqueness does.
    merged = {}
    for name, key in COLLECTIONS:
        seen = {}
        for r in history.get(name, []):
            seen.setdefault(r[key], r)
        fresh = set()
        for i, r in enumerate(suffix.get(name, [])):
            if r[key] in fresh:
                fail("identity_conflict", "/snapshot/%s/%d/%s" % (name, i, key), 5)
            fresh.add(r[key])
            old = seen.get(r[key])
            if old is None:
                seen[r[key]] = r
            elif canonical_json(old) != canonical_json(r):
                fail("identity_conflict", "/snapshot/%s/%d" % (name, i), 3)
        # Canonical collection order: ascending identity.
        merged[name] = [seen[k] for k in sorted(seen)]
    out = dict(history)
    out.update(merged)
    out["cursors"] = _merge_cursors(history.get("cursors", []), suffix.get("cursors", []))
    return out


def _merge_cursors(history, suffix):
    """Cursor per stream: the maximum position of the retained and suffix cursors."""
    by = {c["stream_id"]: c for c in history}
    for c in suffix:
        old = by.get(c["stream_id"])
        if old is None or c["position"] > old["position"]:
            by[c["stream_id"]] = c
    return [by[k] for k in sorted(by)]
