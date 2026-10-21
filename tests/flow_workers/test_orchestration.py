"""Worker boundary tests; numerical expectations belong to independent fixtures."""
import unittest
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from option_flow_workers import FlowExecutionConfig, FlowWorkerError
from option_flow_workers import executor as e

CONFIG = FlowExecutionConfig("batch", 1, 1, 1, 1, 268435456, 268435456)

class WorkerBoundaries(unittest.TestCase):
    def test_unsupported_modes_precede_verification_and_evaluation(self):
        with patch.object(e, "require_verified_flow_cohort") as verify:
            with self.assertRaises(FlowWorkerError) as caught:
                e.execute_flow(None, None, run_key="run1", config=replace(CONFIG, mode="live"), verified_cohort=None)
            self.assertEqual(caught.exception.code, "unsupported_mode")
            verify.assert_not_called()

    def test_parallel_and_boolean_resources_rejected(self):
        for field, value in (("max_workers", 2), ("max_inflight", 2), ("io_slots", 2),
                             ("backend_threads", 2), ("max_workers", True)):
            with self.subTest(field=field, value=value), self.assertRaises(FlowWorkerError) as caught:
                e.execute_flow(None, None, run_key="run1", config=replace(CONFIG, **{field:value}), verified_cohort=None)
            self.assertEqual(caught.exception.code, "unsupported_resources")

    def test_reservation_is_at_least_256_mib_and_within_budget(self):
        for config in (replace(CONFIG, logical_task_bytes=1), replace(CONFIG, memory_budget_bytes=1)):
            with self.assertRaises(FlowWorkerError) as caught:
                e.execute_flow(None, None, run_key="run1", config=config, verified_cohort=None)
            self.assertEqual(caught.exception.code, "resource_limit")

    def test_busy_owner_does_not_enter_action(self):
        self.assertTrue(e._OWNER.acquire(blocking=False))
        try:
            with self.assertRaises(FlowWorkerError) as caught:
                e.execute_flow(None, None, run_key="run1", config=CONFIG, verified_cohort=None)
            self.assertEqual(caught.exception.code, "resource_busy")
        finally:
            e._OWNER.release()

    def test_exception_releases_owner(self):
        with self.assertRaises(FlowWorkerError):
            e._owned(lambda: (_ for _ in ()).throw(ValueError("failed")))
        self.assertEqual(e._owned(lambda: 23), 23)

    def test_cancellation_requires_exact_bool(self):
        with self.assertRaises(FlowWorkerError) as caught:
            e._cancelled(SimpleNamespace(is_cancelled=lambda: 1))
        self.assertEqual(caught.exception.code, "input_invalid")
        self.assertFalse(e._cancelled(None))

    def test_pre_admission_cancellation_returns_no_output(self):
        cancel = SimpleNamespace(is_cancelled=lambda: True)
        with patch.object(e, "require_verified_flow_cohort"), patch.object(e, "_identity", return_value=("a"*64, "b"*64, "c"*64, "d"*64, None)), patch.object(e, "inspect_flow_resources") as admission:
            result = e.execute_flow(None, None, run_key="run1", config=CONFIG, verified_cohort=None, cancellation=cancel)
        self.assertEqual((result.outcome, result.results, result.output_checkpoint, result.commit_receipt), ("cancelled", (), None, None))
        admission.assert_not_called()

    def test_replay_duplicate_keys_precede_execution(self):
        config = replace(CONFIG, mode="chronological_cut_replay")
        with patch.object(e, "_run") as run:
            with self.assertRaises(FlowWorkerError):
                e.execute_flow_replay(None, (None, None), run_keys=("same", "same"), config=config, verified_cohort=None)
            run.assert_not_called()

    def test_run_key_is_closed_ascii(self):
        for key in ("", "x y", "x\n", "ÃƒÂ¼", "x"*129, True):
            with self.subTest(key=key), self.assertRaises(FlowWorkerError):
                e.execute_flow(None, None, run_key=key, config=CONFIG, verified_cohort=None)

    def test_after_commit_cancellation_retains_successful_generation(self):
        from option_flow_io import FlowCommitReceipt
        cancel = SimpleNamespace(value=False)
        cancel.is_cancelled = lambda:cancel.value
        snapshot = SimpleNamespace(**{name:() for name in (
            "bindings", "references", "executions", "quotes", "groups", "populations",
            "context_certificates", "baselines")})
        def steps(*args, **kwargs):
            yield None
            return ()
        class Sink:
            def publish(self, publication):
                self.publication = publication
                cancel.value = True
                return FlowCommitReceipt("run1", "a"*64, "e"*64, "f"*64, None, 0, "committed", True)
            def read(self, key):
                return self.publication
        with ExitStack() as stack:
            for name in ("require_verified_flow_cohort", "inspect_flow_resources", "flow_validate_results",
                         "encode_flow_results", "encode_flow_publication"):
                stack.enter_context(patch.object(e, name))
            stack.enter_context(patch.object(e, "_identity", return_value=("a"*64, "b"*64, "c"*64, "d"*64, None)))
            stack.enter_context(patch.object(e, "_checkpoint", return_value=None))
            stack.enter_context(patch.object(e, "flow_record_digest", side_effect=lambda kind,value: "e"*64 if kind == "flow_publication" else "f"*64))
            stack.enter_context(patch.object(e, "flow_canonical_bytes", return_value=b"complete-publication"))
            stack.enter_context(patch("option_flow_features.engine._evaluate_steps", side_effect=steps))
            result = e.execute_flow(snapshot, None, run_key="run1", config=CONFIG, verified_cohort=None, sink=Sink(), cancellation=cancel)
        self.assertEqual(result.outcome, "committed")
        self.assertTrue(result.cancellation_observed)
        self.assertIsNotNone(result.commit_receipt)

    def test_cancel_between_pure_reducer_steps_closes_generator_without_publication(self):
        cancel = SimpleNamespace(value=False)
        cancel.is_cancelled = lambda:cancel.value
        closed = []
        def steps(*args, **kwargs):
            try:
                cancel.value = True
                yield None
                self.fail("Cancelled reducer must not resume")
            finally:
                closed.append(True)
        snapshot = SimpleNamespace(**{name:() for name in (
            "bindings", "references", "executions", "quotes", "groups", "populations",
            "context_certificates", "baselines")})
        sink = SimpleNamespace(publish=lambda unused:self.fail("Cancelled execution cannot publish"))
        with patch.object(e, "require_verified_flow_cohort"), patch.object(e, "_identity", return_value=("a"*64, "b"*64, "c"*64, "d"*64, None)), patch.object(e, "inspect_flow_resources"), patch("option_flow_features.engine._evaluate_steps", side_effect=steps):
            result = e.execute_flow(snapshot, None, run_key="run1", config=CONFIG, verified_cohort=None, sink=sink, cancellation=cancel)
        self.assertEqual((result.outcome, result.results, result.output_checkpoint), ("cancelled", (), None))
        self.assertEqual(closed, [True])

    def test_cancellation_during_final_verification_prevents_compute_return_or_publish(self):
        for publication in (False, True):
            with self.subTest(publication=publication):
                cancel = SimpleNamespace(value=False)
                cancel.is_cancelled = lambda:cancel.value
                calls = []
                # Initial, pre-computed-return, and pre-publication verifications.
                # Flip at exactly the last applicable verification boundary.
                def verify(unused):
                    calls.append(True)
                    if len(calls) == (3 if publication else 2):
                        cancel.value = True
                def steps(*args, **kwargs):
                    yield None
                    return ()
                snapshot = SimpleNamespace(**{name:() for name in (
                    "bindings", "references", "executions", "quotes", "groups", "populations",
                    "context_certificates", "baselines")})
                sink = SimpleNamespace(publish=lambda unused:self.fail("Cancellation during verification cannot publish")) if publication else None
                with ExitStack() as stack:
                    for name in ("inspect_flow_resources", "flow_validate_results", "encode_flow_results", "encode_flow_publication"):
                        stack.enter_context(patch.object(e, name))
                    stack.enter_context(patch.object(e, "require_verified_flow_cohort", side_effect=verify))
                    stack.enter_context(patch.object(e, "_identity", return_value=("a"*64, "b"*64, "c"*64, "d"*64, None)))
                    stack.enter_context(patch.object(e, "_checkpoint", return_value=None))
                    stack.enter_context(patch("option_flow_features.engine._evaluate_steps", side_effect=steps))
                    result = e.execute_flow(snapshot, None, run_key="run1", config=CONFIG, verified_cohort=None, sink=sink, cancellation=cancel)
                self.assertEqual((result.outcome, result.results, result.output_checkpoint, result.commit_receipt), ("cancelled", (), None, None))
                self.assertEqual(len(calls), 3 if publication else 2)

if __name__ == "__main__":
    unittest.main()
