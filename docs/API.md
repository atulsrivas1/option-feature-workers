# R25 worker API candidate

## Separate R26 flow worker API

`option-flow-workers==0.1.0a1` exports `option_flow_workers.execute_flow`, `execute_flow_replay`, `execute_flow_restore`, `inspect_flow_resources` and `verify_flow_installed` with separate `FlowExecutionConfig`/cohort records. The full closed runtime is contracts/features/I/O/workers at0.1.0a1 plus DuckDB1.5.6; pure calculations use contracts/features only. Supported modes are batch, chronological-cut replay and bounded full-prefix checkpoint restore, each one worker/inflight/I/O/backend thread. Logical admission is not an RSS bound; cancellation/retry preserve actual committed generations. The original R25 API and six-distribution verifier below are unchanged.

The [R26 API index](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/README.md), [typed signatures/codecs/status/evidence](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/FLOW_CONTRACT.md), [mathematics](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/MATHEMATICS.md), [output/profile bindings](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/FEATURE_BINDINGS.json), [compatibility](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/COMPATIBILITY.json), [pure example](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/examples/r26/README.md) and [current qualification](https://github.com/atulsrivas1/option-features/blob/460dd1ab8c6a7b6d884b2eed69cda7964475c17e/docs/r26/LOCAL_QUALIFICATION.md) distinguish implemented native scope from gated EQ190 equity outputs, which remain unsupported/equity_integration_unqualified. R26 remains UNRELEASED; historical R25 no-runtime text below describes its dated source checkpoint.

Source implementation under [EQ186](https://github.com/atulsrivas1/equity-features/issues/531),
against independently reviewed contract freeze
`9403854ff37a7c0b5dbc57c142893a1ce0a262e4` in option-features.
No execution, package build/install, numerical, storage or platform acceptance is
claimed. The protected EQ142 resource hold remains in force until the coordinator
records actual permission to run. The normative contracts remain owned by
[option-features](https://github.com/atulsrivas1/option-features).

`option_feature_workers` exports the frozen `ExecutionConfig`, `Artifact`,
`Cohort`, `ReplayItem`, `RunReceipt`, `CancellationToken` and exact `execute` and
`replay` signatures. It imports canonical types from contracts, result publication
types/codecs from I/O, and the real `option_features.evaluate`; it contains no
pricing, Greek, inverse, source-selection or score implementation.

`execute(snapshot, request, execution, cohort, run_key, sink, cancel)` supports
batch mode only. `replay(items, execution, cohort, sink, cancel)` supports replay
mode only and processes independent snapshots in caller order. Both support only
`max_workers=max_inflight=io_slots=backend_threads=1`. A process-wide nonblocking
owner rejects concurrent/reentrant worker calls rather than creating a queue.
Neither API accepts a numerical callback/plugin or silently upgrades dependencies.

`inspect_resources(snapshot, request, execution)` performs actual typed/count/byte
admission and returns `ResourceAdmission` with wire byte lengths, predicted result
rows, the declared estimate `max(1048576,4*(snapshot+request wire bytes)+4096*rows)`,
reservation bytes and its explicit logical-only limitation. It delegates scalar,
count, canonical-size and solver ceilings to the actual contracts package. The
estimate must fit `logical_task_bytes`, which must fit `memory_budget_bytes`.
These are logical reservations, not measured RSS/native-allocation limits.
Caller-owned objects, returned replay receipts, interpreter/native allocations
and verification file I/O are outside an OS memory sandbox. Arb thread/context
ownership belongs to the qualified pure implementation; no parallel performance
claim is made.

Every run rechecks actual installed artifacts before numerical dispatch, then
binds complete request/snapshot/execution/cohort/worker-wheel content in work
identity. `cohort_digest` computes identity only. It is not artifact proof.
Independent output readiness, reasons and numerical evidence are delegated to the
pure evaluator. Complete selected-output ordering and config/snapshot hashes are
checked before publication. Canonical results must fit the request's byte/row
ceilings.

Cancellation is checked before evaluation, after evaluation returns, and before
publication. It does not interrupt an active solver. Before commit it returns a
`cancelled` receipt with no results or commit receipt. After commit it preserves
actual committed visibility and reports observed cancellation. An exception after
atomic publication triggers a complete equality readback, including bindings;
only an identical committed generation can recover as `already_committed`.
Every successful sink outcome receives another full readback. A changed source,
request, execution or artifact under the same run key conflicts through the sink.
Failures raise typed worker/contract errors rather than success-shaped receipts.
No-sink success is explicitly `computed`, not stored output.

## Installed artifact verification

Additional API, approved by coordinator without changing the frozen execute API:

```python
verify_installed_cohort(cohort, wheel_paths, environment_receipt_path,
                        qualification_manifest,
                        trusted_manifest_sha256) -> InstalledVerification
qualification_manifest_digest(qualification_manifest) -> str
sysconfig_platform() -> str
```

`QualificationManifest(manifest_version="option-qualification1", artifacts=...)`
contains sorted frozen `QualificationSource` records with fields
`distribution`, `version`, `source_commit`, `wheel_sha256`, `source_reference`,
`build_receipt_path`, `build_receipt_sha256`. Paths are local verifier setup, never
canonical numerical inputs/results. `trusted_manifest_sha256` is SHA256 of
`b"option-qualification1\n"` plus canonical JSON of the complete manifest. Obtain
that expected digest from independent coordinator source/artifact review, outside
data-producer claims. A caller-generated hash or a source marker by itself cannot
establish trusted source provenance.

The externally reviewed source/build receipt uses exactly these JSON fields:

```json
{
  "receipt_version": "option-source-build1",
  "distribution": "option-feature-workers",
  "version": "0.1.0a1",
  "source_commit": "<actual reviewed 40 lowercase hex>",
  "wheel_sha256": "<actual wheel SHA256>",
  "source_reference": "<reviewed immutable source reference>",
  "evidence": "<actual source/build/notices evidence reference>"
}
```

Placeholder values above are not accepted evidence. The manifest binds the exact
receipt bytes by SHA256. Project wheels must contain controlled-staging-generated
`<namespace>/_build_identity.json` with exactly `{"source_commit":"<commit>"}`,
included before building the wheel, never injected into an already built wheel.
The coordinator owns source/build provenance attestation. Third-party wheels lack
this project marker and require reviewed immutable source/release references,
exact real wheel hashes and inspected license/native notices in their source
receipts. The verifier checks these bindings; it does not infer git provenance
from a digest, contact the registry, reproduce builds, establish upstream trust
or certify numerical correctness. Calculations never read build metadata.

The verifier requires CPython 3.12, exact Python patch version/platform identity,
the entire installed distribution inventory, all four project packages at
`0.1.0a1`, python-flint `0.9.0`, DuckDB `1.5.6`, plus every installed transitive or
tool distribution in the reviewed cohort. An isolated runtime without pip/build
tools avoids accidentally qualifying unrelated tools. Wheel hashes, METADATA,
complete wheel RECORD hashes/sizes, installed RECORD entries and actual installed
files, project/native module origins and unrecorded package content are checked.
Project namespace markers must agree with the reviewed source/build receipt.
This initial verifier supports direct site-packages wheel layout, not `.data`
relocations, editable installs, symlink packages or unqualified extra scripts.
Encountering such an artifact fails explicitly and requires a reviewed mapping.
Standalone pure `.py` wheel modules are also explicitly unsupported: their
adjacent executable-cache layout requires separate review. Top-level native
extensions such as `_duckdb` remain admitted, with actual origin/file checks and
rejection of adjacent legacy or `__pycache__` bytecode for the module name.
The controlled runtime is installed with `--no-compile` and invoked with
`python -B`, with `sys.pycache_prefix=None`. Every wheel/installed package `.pyc`
or `.pyo`, including unrecorded `__pycache__` content, is rejected. Bytecode is
executable content and is not exempted as harmless installer output. Start in a
clean fresh process with no preexisting package caches; an alternate cache prefix
is not admitted. This profile prevents creating unchecked caches during the
qualified run and fails closed if installed caches appear.

`InstalledVerification` exposes cohort/worker-wheel/manifest digests, checked file
count and generated evidence location. The environment receipt is fresh generated
output, never an input assertion of a previous pass. Setup is remembered only to
locate evidence: every execute reopens/rechecks wheel/source/installed bytes,
inventory, Python/platform and module origins. Missing setup or changed evidence
fails closed. The initial environment is not a hostile-process/filesystem sandbox;
concurrent mutation of Python objects/import state or filesystem during a run is
not admitted. Verification does not secure a malicious process that can monkeypatch
the verifier itself. No production test bypass exists.

`WorkerError` subclasses expose `code` and `work_sha256` when work is available:
`AdmissionError`, `CohortVerificationError`, `ExecutionError`, `PublicationError`.
Contract validation errors remain typed boundary failures. Actual installed
producer tests, source review and numerical gates remain required before merge.
