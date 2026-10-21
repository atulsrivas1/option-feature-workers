## Owner clarification: local merge evidence — October 20, 2026

The owner reaffirmed that local builds and local test runs provide merge validation. This supersedes older mandatory hosted-CI wording: GitHub Actions completion is not an acceptance or merge prerequisite. Retain independent review, appropriate exact-commit local checks, build/install evidence where applicable, numerical fixtures and integration/release gates. Documentation-only changes use relevant local source/document checks; do not invent package builds for them. Record actual commands, source commit, environment and results. Do not claim unexecuted local checks or infer validation of another platform from a local run. Any actual repository protection conflict must be reported separately; it does not redefine this agreement. Existing ownership/resource reservations remain protected.

# R25 source implementation handoff

Current checkpoint, October 20, 2026: fresh worker
`/root/r25_worker_implementation` authoring canonical EQ186, scoped only to this
repository on `codex/r25-worker-implementation`, base
`73b1c5109d2ce5ff7273071c9a72ba8d87d4b5e1`. Coordinator granted source-only work
after independent freeze review of
`9403854ff37a7c0b5dbc57c142893a1ce0a262e4` and canonical source-policy PR586.
No commit/push is authorized until coordinator actual-diff review.

Coordinator harness finding corrected before independent review: both real sink
constructors now explicitly convert their declared destination `Path` to `str`,
matching the actual frozen I/O constructor. Read-only source inspection confirmed
the current contracts validation/canonical/digest exports, evaluator export, I/O
codec exports and Publication/CommitReceipt field order match worker imports and
calls. This is interface source inspection, not an executed integration check.

Fresh independent source review fixes: the synthetic model facts now declare the
actual admitted `option-bsm1` model ID. Both demo and integration source invoke
finite-scenario status/value/coverage/provenance assertions, so identical
unavailable model results cannot pass by parity alone. The verifier rejects
unsupported standalone pure `.py` wheel layouts and retains native-extension
support with explicit adjacent/cache bytecode rejection. A focused authored test
covers the rejected standalone layout. All checks remain source-only and unrun.

Authored source: exact public frozen worker types/APIs, sequential one-owner
execution/replay, validated count/byte/logical reservation admission,
content-bound work identity, explicit cancellation/commit visibility and full
publication recovery/readback, installed-artifact verifier anchored to an
externally reviewed source/build manifest, nonnumerical orchestration/structural
wheel tests, actual-producer integration harness and synthetic stored-output
browser-demo source. No formulas, canonical records or sink schema were copied
into workers. Public contract and I/O exports were coordinated with their fresh
authors. [API.md](API.md) records the auxiliary verifier schema and trust limits.

Executed source checks only: Windows x86-64 CPython 3.12.10,
`python -c` using stdlib `ast.parse` on nine authored Python files, passed;
`git diff --check`, passed for tracked differences. These are checks on an
uncommitted working candidate against the base above, not exact-head local merge
evidence. Full source/JSON/TOML/whitespace receipts are retained at
`qualification/SOURCE_CHECKS.json` once regenerated for the final authoring
candidate. No package imports, runtime tests, type checks, fixture generators,
builds, installs, numerical computations, benchmarks, databases or browser demos
ran. Actual supported-platform/build/numerical/integration acceptance is open.

Resume: coordinator reviews actual source diff and resolves findings; preserve
the original EQ142 protected runtime hold until actual coordinator release.
After that, review actual producer source, build controlled-stage exact artifacts
with source markers/receipts, independently review manifest trust root, execute
appropriate exact-head local unit/install/numerical/integration checks on each
supported platform, obtain fresh independent PR review and actual browser demo.
Hosted Actions completion is not a merge gate. Do not mark EQ186 Done or infer
released/installed/Windows-and-Linux compatibility from source authoring.

## Historical preparation checkpoint

October 20, 2026. Owner selected first option release and dedicated repository homes. option-feature-workers owns: Compose selected option calculations with explicit adapters/sinks, bounded resources, deterministic retry/cancellation and serialized publication. Existing equity task admission/dispatch is not generic option support.

Historical initial baseline: documentation/licensing/work agreements only, with no source package, tests, numerical fixture execution, CI workflow or database. The subsequent contract draft adds a lightweight documentation CI workflow; its presence or success does not establish numerical or installed compatibility. The coordinator prepares reviewed canonical option and cross-layer contracts under GOV037 #581. Existing equity quantity units, result codecs, sink schemas and worker identity admission are incompatible with native option facts without a reviewed extension.

Current owner decision (October 20, 2026): R25 may proceed independently of the former blanket R18/EQ146 and EQ143/EQ144 delivery prerequisites. R17/EQ141 remains the accepted reference; R18 status and active ownership are unchanged. R25 must review and freeze its own contracts/interface choices, qualify its selected exact artifacts and executor/resource behavior, and pass independent numerical, cross-platform and integrated release gates. None of those gates is claimed passed here.

Next: inspect canonical #581 and the revised coordinator agreement; resolve and independently review the concrete R25 contracts and named scopes; pin reviewed contracts before fresh implementation workers. Keep exact artifact/platform qualification under EQ187 and execution/resource qualification under EQ186, with EQ185 responsible for transport/storage conformance. Preserve any current EF1/R18 owner and reserved resource window. Do not claim Ready, numerical parity, installed compatibility, benchmark or release acceptance from these documents.
