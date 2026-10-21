"""Actual installed producer orchestration qualification, after the runtime hold.

This exercises real contracts, calculations, codecs and DuckDB sink. It is not
an independent numerical oracle. Failure exits nonzero; no missing-config skip.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from stored_demo import NeverCancel, load_configuration
from synthetic_scenario import assert_scenario_results, scenario

from option_feature_contracts import canonical_bytes
from option_feature_io import DuckDBSink
from option_features import evaluate
from option_feature_workers import (
    AdmissionError, CohortVerificationError, ExecutionConfig, PublicationError,
    ReplayItem, execute, replay,
)


class CancelAtCheck:
    def __init__(self, check):
        self.check = check
        self.calls = 0

    def is_cancelled(self):
        self.calls += 1
        return self.calls >= self.check


class CancelAfterCommit:
    """Qualification-only sink wrapper; actual publication still uses DuckDB."""
    def __init__(self, sink, token):
        self.sink = sink
        self.token = token

    def commit(self, publication):
        receipt = self.sink.commit(publication)
        self.token.check = 0
        return receipt

    def read(self, run_key):
        return self.sink.read(run_key)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--trusted-manifest-sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    cohort = load_configuration(args.config, args.trusted_manifest_sha256, destination)
    batch = ExecutionConfig("batch", 1, 1, 67108864, 16777216, 1, 1)
    sink = DuckDBSink(str(destination / "integration.duckdb"))
    evidence = []
    for variant in ("complete", "unsupported", "missing_spot", "future_spot", "partial_quotes"):
        snapshot, request = scenario(variant)
        direct = evaluate(snapshot, request)
        assert_scenario_results(variant, direct)
        first = execute(snapshot, request, batch, cohort, variant, sink, NeverCancel())
        require(first.outcome in ("committed", "already_committed"), "No committed generation")
        second = execute(snapshot, request, batch, cohort, variant, sink, NeverCancel())
        require(second.outcome == "already_committed", "Identical retry was not idempotent")
        stored = sink.read(variant)
        require(stored is not None and canonical_bytes(direct) == canonical_bytes(first.results)
                == canonical_bytes(second.results) == canonical_bytes(stored.results), "Complete canonical parity failed")
        assert_scenario_results(variant, first.results)
        assert_scenario_results(variant, stored.results)
        replay_receipt, = replay((ReplayItem(snapshot, request, "replay-" + variant),),
                                replace(batch, mode="replay"), cohort, sink, NeverCancel())
        replay_stored = sink.read("replay-" + variant)
        require(replay_stored is not None and canonical_bytes(direct) == canonical_bytes(replay_receipt.results)
                == canonical_bytes(replay_stored.results), "Replay complete canonical parity failed")
        assert_scenario_results(variant, replay_stored.results)
        changed = replace(snapshot, bindings=(replace(snapshot.bindings[0], source_revision="changed-source"),))
        try:
            execute(changed, request, batch, cohort, variant, sink, NeverCancel())
        except PublicationError:
            pass
        else:
            raise RuntimeError("Changed work was allowed to reuse a committed key")
        require(sink.read(variant) == stored, "Conflict changed previously stored data")
        evidence.append({"scenario": variant, "full_result_parity": True,
                         "scenario_semantics_verified": True,
                         "retry_verified": True, "changed_source_conflict_verified": True,
                         "batch_work_sha256": first.work_sha256,
                         "replay_work_sha256": replay_receipt.work_sha256})
    snapshot, request = scenario()
    for check in (1, 2, 3):
        key = "cancel-at-" + str(check)
        receipt = execute(snapshot, request, batch, cohort, key, sink, CancelAtCheck(check))
        require(receipt.outcome == "cancelled" and receipt.results == ()
                and receipt.commit_receipt is None and sink.read(key) is None,
                "Cancellation published or returned results")
    token = CancelAtCheck(1000)
    receipt = execute(snapshot, request, batch, cohort, "cancel-after-commit",
                      CancelAfterCommit(sink, token), token)
    require(receipt.outcome in ("committed", "already_committed") and receipt.cancellation_observed,
            "Cancellation erased committed visibility")
    require(sink.read(receipt.run_key) is not None, "Committed cancellation output is absent")
    for bad in (replace(batch, max_workers=2), replace(batch, logical_task_bytes=1)):
        try:
            execute(snapshot, request, bad, cohort, "bad-resources", sink, NeverCancel())
        except AdmissionError:
            pass
        else:
            raise RuntimeError("Unsupported resource configuration was admitted")
    changed_cohort = replace(cohort, artifacts=tuple(replace(item, source_commit="0" * 40)
                                                     if item.role == "workers" else item for item in cohort.artifacts))
    try:
        execute(snapshot, request, batch, changed_cohort, "unverified", sink, NeverCancel())
    except CohortVerificationError:
        pass
    else:
        raise RuntimeError("Unconfigured digest-looking artifact cohort was admitted")
    (destination / "integration-evidence.json").write_text(json.dumps({
        "evidence_version": "r25-worker-integration1", "scenarios": evidence,
        "pre_post_precommit_cancellation": True, "postcommit_visibility": True,
        "unsupported_resources_rejected": True, "unverified_cohort_rejected": True,
        "independent_numerical_acceptance": False,
        "limitation": "Real producer integration parity, not a mathematical oracle or other-platform proof."}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
