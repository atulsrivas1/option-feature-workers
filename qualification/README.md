# R25 worker qualification — not run

Everything here is source prepared while the original EQ142 protected runtime
reservation is held. No command below has been executed as part of authoring.
The coordinator must record the actual hold release before imports/tests/builds,
installs, numerical generation or DuckDB operations. Source checks do not lift it.

After source/diff review, build all actual project producers from reviewed exact
commits in controlled staging directories. Generate `_build_identity.json`
before each wheel build and retain exact source-tree/build commands and receipts.
Produce wheels and sdists. Install wheels in a clean CPython 3.12 runtime using an
external installer, exact reviewed transitive/platform wheels and no implicit
downloads. Separately install the sdist-built project wheels and validate their
source/build bindings. Never rewrite a wheel after RECORD creation. Inspect
python-flint's complete native license/notices and platform identities rather
than labelling the binary dependency MIT-only. [API.md](../docs/API.md) defines
the actual source/build receipt and externally trusted manifest schema.

The local configuration file has exactly `cohort`, `qualification_manifest`,
`wheel_paths`. Cohort and manifest use the public frozen record field names;
artifact/source arrays are sorted by normalized distribution name. Evidence paths
are real paths on the current platform. The independently reviewed expected
manifest digest must be supplied separately on the command line, not copied from
a producer's input data. Include every distribution actually installed; a private
empty runtime with exact installed producer/backend wheels is simplest. Install
with `--no-compile`, retain no package `.pyc`/`.pyo` caches, start a fresh process
with `python -B` and no `PYTHONPYCACHEPREFIX`. The verifier rejects executable
bytecode caches rather than treating them as harmless installer metadata.
Process/filesystem integrity is an external runtime assumption; this is not a
malicious-process sandbox. Do not run these commands in a mutable shared runtime.

The intended commands, in the installed runtime after hold release, are:

```text
python -B -m unittest discover -s packages/workers/tests -v
python -B qualification/run_integration.py --config <actual-config.json> --trusted-manifest-sha256 <reviewed-digest> --destination <new-evidence-directory>
python -B examples/stored_demo.py --config <actual-config.json> --trusted-manifest-sha256 <reviewed-digest> --destination <new-demo-directory>
```

The unit suite explicitly isolates nonnumerical control flow with fake sinks and
private collaborator patches; it cannot satisfy numerical/artifact/integration
acceptance. The integration harness uses actual pure calculations, strict codec
storage and complete canonical direct/batch/replay/stored parity. Independent
finite-scenario semantic assertions also require available computed model outputs
for the complete case, exact unsupported/missing/future statuses, unaffected
reference values, and the partial quote ratio/counts/flag; parity alone cannot
make an unavailable scenario pass. Broad model sign/range checks are not a
numerical oracle. The synthetic ModelFact profile is explicitly `option-bsm1`.
It exercises
unsupported/missing/future/partial scenarios, same-key retries, changed-source
conflicts, pre/post-evaluation and precommit cancellation, committed visibility,
invalid resources and unverified-cohort rejection. Those checks do not establish
independent mathematical correctness. Run actual independent numerical fixture
acceptance in the producer suite and preserve its exact artifacts/results too.

The stored demo emits actual DuckDB readback into local HTML and evidence JSON;
the browser must actually be opened and inspected by the coordinator. Generating
HTML is not browser-demo evidence. No server, deployment, provider feed, registry
publication, benchmark or notification is performed by these commands.

Record actual command lines, source commits, wheel/sdist hashes, dependency/native
versions/notices, interpreter/platform, exit codes and complete result evidence.
Windows x86-64 and Linux x86-64 require separate actual local runs. One platform's
run never proves the other. Canonical byte equality across both outputs is a
separate comparison. Test installed-file/wheel/RECORD/source-receipt/module-origin
tampering in disposable environments; verify each next execute fails instead of
accepting prior cached success. Keep protected study resources and unrelated
databases intact. Unsupported wheel layouts or missing exact artifacts are named
blockers, not automatic source builds or hidden policy exceptions.
