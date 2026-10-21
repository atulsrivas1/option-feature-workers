# Option feature workers

Sequential, content-bound orchestration of supplied option snapshots, pure calculations and optional atomic storage. Workers compose [option-features](https://github.com/atulsrivas1/option-features) and [option-feature-io](https://github.com/atulsrivas1/option-feature-io); they implement no feature mathematics.

**R25 / option-feature-workers 0.1.0a1 is UNRELEASED and under qualification.** Final numerical, rebuilt-artifact, integration and inspected browser-demo acceptance remain open. See [release notes](docs/R25_RELEASE_NOTES.md), [EQ186](https://github.com/atulsrivas1/equity-features/issues/531) and [R25 acceptance](https://github.com/atulsrivas1/equity-features/issues/532). No PyPI publication, production service or performance claim is made.

## Execute supplied snapshots

The module exports typed `ExecutionConfig`, `Artifact`, `Cohort`, `ReplayItem`, `RunReceipt` and cancellation/error types. Given typed caller-supplied inputs and an already verified installed cohort:

```python
from option_feature_workers import execute, replay

receipt = execute(snapshot, request, execution, cohort, run_key, sink, cancel)
receipts = replay(items, replay_execution, cohort, sink, cancel)
```

`execute` requires batch mode. `replay` processes a tuple of independent snapshots in caller order using replay mode. Only `max_workers=max_inflight=io_slots=backend_threads=1` is admitted; concurrent/reentrant calls fail. No incremental update/restore/partition merge is delivered.

Requests select the library's nine matrix outputs and five foundation outputs; [library scope/units](https://github.com/atulsrivas1/option-features/blob/codex/r25-library-implementation/README.md) distinguish absolute/signed delta and original `option-quote-count1` / `option-chain-breadth1` definitions. No private-score parity or complete option-matrix coverage is implied. Supplied spot needs no unused equity dependency; equity packages never import options.

`inspect_resources` validates actual counts/bytes/predicted result rows against logical reservations/budget. These are not OS/native RSS bounds. Work identity binds snapshot, request, execution and exact artifact cohort. Publication requires full readback; no-sink success is `computed`. Recovery after an exception requires an identical complete committed publication. Cancellation checks before/after evaluation and before publication do not interrupt an active solver or erase actual commits. See the [API](docs/API.md).

The [typed synthetic scenario](examples/synthetic_scenario.py) supplies original facts and explicit finite-population coverage. The [stored demo](examples/stored_demo.py) composes evaluation, execution and DuckDB readback into local HTML. Matching paths and scenario assertions supplement independent numerical fixtures; they do not replace them. Browser inspection is separate evidence from HTML generation.

## Install and verify a cohort

CPython `>=3.12,<3.13`; exact direct dependencies `option-feature-contracts==0.1.0a1`, `option-features==0.1.0a1`, `option-feature-io==0.1.0a1`. Selected native backends are `python-flint==0.9.0` and `duckdb==1.5.6`.

Install reviewed locally qualified wheels with a complete platform lock and hashes. Replace placeholders with actual qualification artifacts:

```text
python -m pip --python <clean-runtime-python> install --no-index --find-links <qualified-wheelhouse> --require-hashes --no-compile -r <reviewed-platform-lock.txt>
```

No registry availability is implied. Controlled staging generates build identities before wheel construction; source/editable installation alone does not establish provenance. See the [qualification guide](qualification/README.md).

Call `verify_installed_cohort` with actual wheel paths, source/build receipts, complete qualification manifest and separately trusted digest. Every execute rechecks wheel hashes, installed RECORD/file content, module origins, distribution inventory, Python patch and platform. A version or prior receipt is not proof. This assumes a trusted stable process/filesystem; it is not a hostile-process sandbox.

The runtime uses fresh `python -B`, no package `.pyc`/`.pyo` caches, no alternate cache prefix and no preexisting caches. Unqualified layouts/editable installs fail closed. Every installed distribution, including tools retained in the runtime, must belong to the reviewed cohort. Single-thread native configuration establishes no throughput claim.

[Implementation PR](https://github.com/atulsrivas1/option-feature-workers/pull/2), [releases](https://github.com/atulsrivas1/option-feature-workers/releases), [R25 epic](https://github.com/atulsrivas1/equity-features/issues/526), [version policy](docs/VERSIONING.md), [handoff](docs/SESSION_HANDOFF.md), [work agreements](AGENTS.md).

Own code is [Apache-2.0](LICENSE). Dependencies/bundled native components retain separate licenses/notices; Apache-2.0 does not relicense them or grant provider/private-data rights.
