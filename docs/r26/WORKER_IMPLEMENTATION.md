# R26 flow worker source checkpoint

Canonical story: [EQ192 #538](https://github.com/atulsrivas1/equity-features/issues/538).
Author: fresh layer worker `/root/r26_native_worker_implementation`, October 21, 2026.
Base: `191a2fe8f744bdbea36b29fabc209dfdc5359d94` on `codex/r26-flow-workers`.
Frozen source contract: library `d1fce33945832c78ea039efd41408564a8d382c2`, merged
`f78e9c26a298b213fb54c129e09546e2744d7530`, tree
`8918dc707ab5c9dd5cbc9ee513e3b048eef3dc1c`.

This is authored source, not a qualified execution/release. Source-only admission
is the coordinator's external R26 native-authoring grant; no R25 runtime reservation
or equity producer acceptance is inherited. Actual EQ153/EQ158 integration remains
required for EQ190 and full R26. Hosted CI is optional; appropriate exact-source
local checks and fresh independent review remain required.

## Added implementation

Only the new `packages/flow-workers`, `tests/flow_workers`, `tools/flow_*` and this
checkpoint are owned here. All old R25 source, manifests, tests and entry points
remain unchanged. The new `option-flow-workers==0.1.0a1` distribution imports only
the new flow family and standard library. It does not add flint or an R25 runtime
import. Its actual closed runtime comprises the four new flow distributions and
DuckDB1.5.6, with exactly pinned dependency metadata.

The worker serializes one complete invocation using a process-wide nonblocking
owner lock. Unsupported modes/resources fail before producer/sink entry. Static
resource accounting charges encoded snapshot/request/input-checkpoint bytes,
recursive record count and predicted rows against a minimum256MiB logical task
reservation. This reservation is not enforced RSS or native allocation control.
There are no throughput or global idle-host claims.

Batch consumes the pure calculation step generator. Cancellation is polled before
admission, during record preparation, between pure reducer steps, after full result
encoding and immediately before transaction entry. Calculation code receives no
cancellation object, storage callback or I/O dependency. The generator closes on
cancellation/error. A successful committed generation survives later cancellation;
its returned outcome remains committed/already_committed with cancellation observed.

Chronological replay consumes successive cuts of one immutable ledger, validates
nondecreasing clocks/cursors and stable policy/group/output/window-start identities,
and publishes each cut separately. Cancellation stops subsequent cuts; committed
prior generations are retained. Restore uses the pure library's full-history merge
helper, not a cached sign accumulator, and binds the actual merged snapshot plus
input checkpoint into work/result/publication hashes. It recomputes complete
history. Batch recomputation is not described as incremental/live.

Before publication the worker validates evaluator invocation hashes, serializes all
results and optional checkpoint, and freshly re-verifies the installed cohort.
After sink publication it checks every receipt identity/count/outcome and performs
complete canonical publication readback. Real sink atomicity/retry/uncertain-commit
recovery belongs to the new I/O sink. No mock/unit boundary test establishes actual
DuckDB correctness or numerical fixture acceptance.

## Artifact trust

`verify_flow_installed` requires an external independently reviewed manifest digest.
It checks the exact five-distribution set/versions/roles, interpreter/platform,
archive hashes, source/build receipts, own embedded build markers, DuckDB upstream
source identity and bundled rights notices, wheel/installed RECORD bytes and sizes,
module origins, links, extra executable files and package-directory contents. A
cached registration only retains evidence locations; every execute and publication
rehashes real evidence. A changed registered installation raises `cohort_changed`.
The generated environment receipt records current installed inventory/origins and
cohort/artifact/manifest hashes; it does not authorize itself.

`tools/flow_candidate_lock.py` prepares an untrusted candidate from actual wheels
and actual source/build receipts. It refuses overwrite and prints `authorized:false`.
The coordinator must review sources/artifacts/receipts out of band before its digest
can become an execution trust anchor. No fake current lock, wheel digest, build
receipt or qualified platform claim is committed.

## Checks and pending qualification

Actual source check: CPython `python -B` with standard-library `ast.parse` over all
new Python files. JSON parsing/hash inspection of the six frozen contract documents
was source inspection only. No new production import, numerical test, package build,
installation, database operation or benchmark has been executed by this worker.

Authored unit tests cover unsupported profiles/resources, owner contention and
release after exceptions, exact cancellation protocol, pre-admission and
between-reducer cancellation, post-commit cancellation retention, replay key
admission, unanchored/extra/missing/future-version/native-source cohort rejection.
These tests remain unexecuted at this source checkpoint.

Next: coordinator source review; actual completed library/I/O producers; explicit
serialized runtime lease; local boundary tests and independent materialized fixture
integration. Then exact-source wheel/sdist builds, isolated pip-free Windows/Linux
cohorts, tamper tests, complete direct/worker/stored parity, genuine cut replay and
restore, transaction fault/cancellation/retry tests, bounded measured resource
workloads and actual stored-output browser inspection. R25 regressions use their
unchanged original separate six-distribution cohort. Merged native source is not
full R26 acceptance or publication authority.

## Independent source review rework

Fresh independent reviewer `/root/r26_native_worker_independent_review` found two
source defects before runtime qualification: descendant modules/package search
paths were not covered by top-level origin checks (P1), and cancellation could
arrive during the final cohort verification before transaction entry/computed
return without a subsequent poll (P2). This was a failed initial source review;
no prior numerical/artifact acceptance is implied.

Correction: verification derives every importable source/extension descendant
from reviewed wheel members, checks loaded module file/spec origins and package
search locations, and resolves each descendant through the current meta path
without importing modules. Undeclared loaded descendants are rejected. The worker
now polls immediately after final verification before returning computed results
or entering publication. No abort is introduced after the transaction boundary.

Four new origin regressions cover loaded-submodule shadowing, package-search-path
tampering, import-finder descendant shadowing, and an unimported exact-origin
control. A fifth new test flips cancellation inside final verification for both
computed and publication paths. The original16 tests and these5 additions remain
unexecuted (21 authored test methods total); actual validation here is AST-only.
A calculation-layer development lease held by another worker prohibits runtime
use by this worker until the coordinator grants a separate lease. Fresh independent
re-review is pending; no commit/push is authorized yet.

## Exact-source artifact builder authored

`tools/flow_build_artifacts.py` is a separate source-only candidate helper. It has
not been executed/imported here; no artifact was built. It accepts explicit three
repository paths/40-hex commits, an existing prepared builder interpreter, an actual
DuckDB1.5.6 platform wheel and a new private output directory outside those repos.
No source working tree is modified and no package install/verification/publication
or network acquisition is performed. Runtime requires its own coordinator lease.

The helper archives only four constant flow package paths from the exact selected
commits, validates safe regular-file extraction, inventories archived source hashes,
and overlays only each private staged `_build_identity.json`. It checks exact
setuptools80.9.0 backend/profile and records actual builder Python/platform and
build/wheel/packaging versions. Original wheel/sdist construction and rebuilding
that actual sdist use `--no-isolation`; subprocess environments disable pip network
indexes/user-site/PYTHONPATH. Every attempted command, actual output, exit code and
failure is retained. Source archives/staged files, original/rebuilt artifacts and
complete wheel member parity are separately hashed; archive-byte equality is not
confused with wheel member parity or runtime qualification.

The supplied DuckDB wheel must match actual builder tags and metadata, retains
actual bundled notices and records its real archive/member hashes. The native
receipt preserves upstream source802a345bb627435d2a05d63cb74454fa98b60b5e and explicitly
makes no upstream reproducible-build/authorship claim. The helper emits exact
`option-flow-source-build1` receipts plus five-entry candidate lock inputs for each
artifact form; these never configure cohort verification or authorize themselves.
An external independent coordinator review must establish actual trust anchors.

Four additional authored archive-regression methods cover literal extraction,
traversal/absolute/Windows-device/link rejection before source writes, normalized
duplicate rejection and refusal to reuse existing staging. These are unexecuted;
the earlier21 methods remain unexecuted by this author. Actual source validation
for this addition is AST parsing only. Independent source review and all actual
build/install/platform/tamper/numerical gates remain pending.

## Local development evidence and retained failed attempts

The preceding unexecuted statements describe the earlier author checkpoints.
Subsequent local Windows development checks were performed by the coordinator
under released, serialized leases R26-WORKERS-DEV01/02/03. Each ran
`python -B -m unittest discover -s tests/flow_workers -v` against the source
checkout and recorded identical before/after producer and test hashes within
that attempt. These are source-development checks, not installed-cohort or
cross-platform qualification. The coordinator retains the complete command
output and source inventories in the three corresponding private lease receipts.

DEV01 exited 1: 25 methods ran in 0.240s, with one positive-control assertion
failure because Windows supplied a short temporary-directory spelling while the
verifier correctly returned its resolved long spelling. The coordinator changed
only that expected path to `str((package / "engine.py").resolve())`; production
verification was unchanged. DEV02 exited 1 because the first test edit introduced
an indentation error: 17 loader/test entries ran in 0.159s, including the failed
module import. After correcting indentation, DEV03 exited 0: all 25 methods passed
in 0.217s (command elapsed 1.005043899989687s). Both failed attempts are preserved;
neither is reported as a successful full suite.

Independent reviewer `/root/r26_native_worker_independent_review` inspected the
one-assertion correction and those actual receipts. Resolving the expected path
preserves the positive-control requirement that accepted module origins equal
the exact installed path; it does not weaken shadow-origin rejection. The final
test file SHA256 is
`a9bafc295c3b43118be20b8b8126122c1565b1f776320f99aaefe4b01c94cfca`.

Earlier, the same reviewer executed only
`python -I -B -m unittest discover -s tests/flow_workers -p test_build_artifacts.py -v`
under released lease R26-BUILDER-UNIT-REVIEW-01: all 4 archive tests passed in 0.125s,
exit 0. That command imported only the helper and standard library and performed
no production imports, package builds, database operations or network access.
The helper/test hashes were respectively
`f2926864f839b6c78faa265fe57c30cb764e29535ec22190e368b57662b6d283` and
`c6f50f7744778a0345e05a2936a144b41c5d27de3950472d0a63416276a32628`.

No real artifact construction, installed five-distribution verification, native
DuckDB descendant compatibility, end-to-end numerical fixture parity, Linux run,
resource measurement or release acceptance is established by these unit checks.
Exact committed-source validation and fresh independent PR review remain next.

## First actual artifact preparation failure

The coordinator attempted exact-source Windows candidate construction. It stopped at the first interpreter metadata inspection before any native-wheel inspection, source archive or package build: the existing prepared builder has no separately installed wheel distribution. That package is not in the frozen setuptools80.9.0 build-system requirements; subsequent actual builds must verify the selected backend artifact support. The helper incorrectly required wheel metadata merely to report an optional tool version. Corrected inspection records null when wheel is absent, retaining mandatory actual CPython/platform/setuptools/build/packaging checks and all artifact gates. No original R25 builder/input was modified. The failed attempt and conservative resource hold/reconciliation remain retained; a new output directory, reviewed helper and new lease are required for retry. No artifact acceptance follows from this correction.

## Installed native-origin profile correction

The coordinator's actual original-wheel installed five-distribution candidate
failed verification with `Loaded undeclared descendant module`. Read-only diagnosis
identified exactly two extension-created DuckDB1.5.6 children, `_duckdb._func` and
`_duckdb._sqltypes`: both point to the already reviewed `_duckdb` native artifact,
have no separate spec/loader/package/search path, and are identical to their
parent's corresponding module attributes. This failure established no installed
cohort admission; prior source reviews and artifact hash agreement did not cover
this native child shape.

A coordinator-authorized closed native-origin profile now permits only these two
literal child names/closed export inventories, only after their parent's actual
wheel origin is verified. Both must be exact ModuleType objects with exact names,
the same native file as that parent, identical parent attribute bindings, and null
spec/loader/package/path metadata. Missing/changed children, extra exports, altered
origins/specs/search paths and every other undeclared descendant remain rejected.
DuckDB version/source/wheel/RECORD/notices checks remain mandatory; no dependency,
formula, fixture expectation or R25 profile changes are introduced.

Eight additional authored native-profile test methods include a literal positive
shape control and rejection of changed child files/metadata/name/type/parent
attributes/export inventory, an unreviewed third child, and lack of a verified
parent. Synthetic modules do not qualify actual native execution. Only AST checks
were executed by this author for this correction. Fresh independent review and
actual installed native/tamper qualification remain pending; no rebuild/runtime,
Git operation or publication was performed here.

## Linux builder executable preparation

Read-only inspection of the existing Linux builder shows bin/python is a virtual-environment symlink. The helper previously resolved that executable to its base interpreter before invocation, which would discard the configured builder prefix on Linux. Before any R26 Linux build attempt, the coordinator changed only executable path handling to preserve its absolute configured path and require an existing file. Mandatory actual CPython/backend/platform inspection remains unchanged; the subsequent actual Linux build must verify the prepared environment. Windows executable paths are preserved equivalently. This is a source-discovered platform defect, not an executed Linux failure or Linux acceptance.

## Native profile source-development validation

Actual R26-WORKERS-DEV04 ran33methods:32passed and the positive-control assertion failed because the Windows temporary parent path used an8.3 alias while verified origins were resolved long paths. Production checks were unchanged; the test now compares the resolved parent path. The preserved retry R26-WORKERS-DEV05 passed all33methods in0.363s (1.143s command elapsed), with identical before/after producer/test hashes and no failures/errors/skips. Eight native-profile methods include deletion of the parent attribute and root import-finder shadow subcases. These are development controls with synthetic module objects, not actual installed native admission. The original installed failure remains retained; new exact artifacts and actual clean-runtime verification are still required.
