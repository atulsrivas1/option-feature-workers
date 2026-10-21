"""NONNUMERICAL orchestration tests, not artifact or release acceptance.

Private collaborators are patched solely to isolate ordering/cancellation/error
control flow. Production has no verification bypass or callback parameter.
Actual producer/wheel/numerical integration remains separately mandatory.
"""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from option_feature_contracts import InputBinding, Result, content_digest
from option_feature_io import CommitReceipt, Publication
from option_feature_workers import (
    AdmissionError, ExecutionConfig, PublicationError, ReplayItem, RunReceipt,
    execute, replay,
)
from option_feature_workers import executor


def result():
    return Result(
        schema_version="option-result1", contract_id="toy", underlying_id=None,
        output_id="contract.dte", currency=None, action_basis_id=None,
        origin="computed", value=None, unit="calendar_days", status="missing_input",
        reason="missing_definition", quality_flags=("missing_definition",), coverage=None,
        solver_evidence=None, pricing_evidence=None, converted_operands=None,
        dependency_binding_ids=(), dependency_record_sha256s=(), valuation_ns=0,
        knowledge_cutoff_ns=0, model_id="not_applicable", formula_version="option-reference1",
        producer_model_id=None, producer_formula_id=None, config_sha256="1" * 64,
        snapshot_sha256="2" * 64, contracts_package_version="0.1.0a1",
        calculation_package_version="0.1.0a1")


def publication():
    return Publication("toy-run", "3" * 64, "1" * 64, "2" * 64, "4" * 64,
                       (result(),), (InputBinding("toy", "synthetic", "1", "5" * 64,
                                                  "synthetic", "original-unit-scenario"),))


class MemorySink:
    def __init__(self, *, fail_after_commit=False, corrupt=False):
        self.value = None
        self.fail_after_commit = fail_after_commit
        self.corrupt = corrupt

    def commit(self, value):
        self.value = value
        if self.fail_after_commit:
            raise OSError("Synthetic transport failure after visibility")
        return CommitReceipt(value.run_key, value.work_sha256,
                             content_digest("results", value.results), len(value.results),
                             "committed", True)

    def read(self, run_key):
        return replace(self.value, cohort_sha256="6" * 64) if self.corrupt else self.value


class PublicationTests(unittest.TestCase):
    def test_full_readback_after_success(self):
        sink = MemorySink()
        receipt = executor._publish(sink, publication())
        self.assertEqual(receipt.outcome, "committed")
        self.assertEqual(sink.value, publication())

    def test_failure_after_commit_recovers_visible_content(self):
        receipt = executor._publish(MemorySink(fail_after_commit=True), publication())
        self.assertEqual(receipt.outcome, "already_committed")
        self.assertTrue(receipt.readback_verified)

    def test_changed_summary_or_bindings_never_passes_recovery(self):
        with self.assertRaises(PublicationError):
            executor._publish(MemorySink(fail_after_commit=True, corrupt=True), publication())

    def test_success_shaped_receipt_without_matching_readback_fails(self):
        with self.assertRaises(PublicationError):
            executor._publish(MemorySink(corrupt=True), publication())


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.batch = ExecutionConfig("batch", 1, 1, 1048576, 1048576, 1, 1)
        self.replay_config = replace(self.batch, mode="replay")

    def test_unqualified_parallel_and_bool_configuration_rejected(self):
        for config in (replace(self.batch, max_workers=2),
                       replace(self.batch, io_slots=True),
                       replace(self.batch, logical_task_bytes=2097152)):
            with self.assertRaises(AdmissionError):
                executor._configuration(config, "batch")

    def test_owner_released_on_failure(self):
        with patch.object(executor, "_execute", side_effect=ValueError("synthetic")):
            with self.assertRaises(ValueError):
                execute(None, None, self.batch, None, "toy", None, None)
        self.assertTrue(executor._OWNER.acquire(blocking=False))
        executor._OWNER.release()

    def test_reentrant_owner_rejected(self):
        executor._OWNER.acquire()
        try:
            with self.assertRaises(AdmissionError):
                execute(None, None, self.batch, None, "toy", None, None)
        finally:
            executor._OWNER.release()

    def test_replay_is_ordered_and_stops_on_cancellation(self):
        items = tuple(ReplayItem(None, None, key) for key in ("a", "b", "c"))
        returned = (RunReceipt("a", "1" * 64, "computed", (), None, False),
                    RunReceipt("b", "2" * 64, "cancelled", (), None, True))
        with patch.object(executor, "_execute", side_effect=returned) as run:
            receipts = replay(items, self.replay_config, None, None, None)
        self.assertEqual(tuple(r.run_key for r in receipts), ("a", "b"))
        self.assertEqual(run.call_count, 2)

    def test_cancel_protocol_must_return_bool(self):
        with self.assertRaises(Exception) as caught:
            executor._cancelled(SimpleNamespace(is_cancelled=lambda: 1))
        self.assertEqual(caught.exception.code, "cancellation_protocol")


if __name__ == "__main__":
    unittest.main()
