"""Checkpoint construction and restore validation (CP0-CP3) for option-flow-variants1.

Pure functions over closed records. Errors use the typed VariantValidationError
from option_feature_contracts.variants1 so the worker can translate them.
"""
from option_feature_contracts.variants1.canonical import (
    FORMULA, SCHEMA_CHECKPOINT, canonical_json, cohort_digest, fail, record_digest,
)

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


def make_checkpoint(history, prior_request, cohort, producer_admission=None):
    """Output checkpoint for a completed run: history is the causal cut of the Snapshot."""
    return {
        "schema_version": SCHEMA_CHECKPOINT,
        "history": history,
        "prior_request": prior_request,
        "history_sha256": record_digest("variant_Snapshot", history),
        "prior_request_sha256": record_digest("variant_Request", prior_request),
        "policy_sha256s": [record_digest("variant_Policy", p) for p in prior_request["policies"]],
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


def validate_restore(checkpoint, request, suffix, cohort_sha256, producer_admission=None):
    """CP1-CP3 checks, then immutable merge. Returns the merged Snapshot.

    cohort_sha256 is the current evaluator cohort digest. Raises
    VariantValidationError with the first failing typed code and pointer.
    """
    # CP1a/CP1b: retained digests must match the retained records they name.
    if checkpoint["prior_request_sha256"] != record_digest("variant_Request", checkpoint["prior_request"]):
        fail("digest_mismatch", "/checkpoint/prior_request_sha256", 1)
    if checkpoint["history_sha256"] != record_digest("variant_Snapshot", checkpoint["history"]):
        fail("digest_mismatch", "/checkpoint/history_sha256", 1)
    # CP2: retained evaluator identity and admission must match the current run.
    if checkpoint["evaluator_cohort_sha256"] != cohort_sha256:
        fail("checkpoint_cut_mismatch", "/checkpoint/evaluator_cohort_sha256", 2)
    if not _admission_prefix_ok(checkpoint["producer_admission"], producer_admission):
        fail("checkpoint_cut_mismatch", "/checkpoint/producer_admission", 2)

    history = checkpoint["history"]
    prior = checkpoint["prior_request"]
    # CP3 (1): current request knowledge may not regress.
    if request["knowledge_K_ns"] < prior["knowledge_K_ns"]:
        fail("checkpoint_cut_mismatch", "/request/knowledge_K_ns", 3)
    # CP3 (2): cut cursor positions may not regress, scanned in current index order.
    retained = {c["stream_id"]: c["position"] for c in prior["cut_cursors"]}
    for i, c in enumerate(request["cut_cursors"]):
        if c["stream_id"] in retained and c["position"] < retained[c["stream_id"]]:
            fail("checkpoint_cut_mismatch", "/request/cut_cursors/%d/position" % i, 3)
    # CP3 (3): immutable merge. Byte-identical retained identities are reusable;
    # a changed record under a retained identity is an identity_conflict.
    merged = {}
    for name, key in COLLECTIONS:
        seen = {}
        for r in history.get(name, []):
            seen.setdefault(r[key], r)
        for i, r in enumerate(suffix.get(name, [])):
            old = seen.get(r[key])
            if old is None:
                seen[r[key]] = r
            elif canonical_json(old) != canonical_json(r):
                fail("identity_conflict", "/snapshot/%s/%d" % (name, i), 3)
        # Canonical collection order: ascending identity, then canonical bytes.
        merged[name] = [seen[k] for k in sorted(seen)]
    out = dict(history)
    out.update(merged)
    out["cursors"] = _merge_cursors(history.get("cursors", []), suffix.get("cursors", []))
    return out


def _merge_cursors(history, suffix):
    """Cursor per stream: the suffix (current cut) position wins over the retained one."""
    by = {c["stream_id"]: c for c in history}
    for c in suffix:
        by[c["stream_id"]] = c
    return [by[k] for k in sorted(by)]
