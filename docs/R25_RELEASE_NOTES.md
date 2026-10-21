# R25 release notes — 0.1.0a1 candidate

**UNRELEASED; final qualification/acceptance pending.** No date/tag, registry publication or final platform pass is claimed. Final exact-artifact acceptance evidence is not yet published; follow [EQ187](https://github.com/atulsrivas1/equity-features/issues/532). Earlier cohort/component runs do not qualify later edits or rebuilt wheels.

## Scope and new APIs

`option-feature-workers==0.1.0a1` adds typed batch `execute`, ordered independent-snapshot `replay`, resource inspection, content-bound receipts, cancellation and optional atomic publication/readback. It delegates all mathematics to `option_features.evaluate`.

One owner/worker/inflight request/I-O slot/backend thread is admitted. Actual count/byte/output-row admission uses logical reservations, not hard RSS/native allocation bounds. Cancellation is observed at boundaries, not inside a solver; committed visibility remains truthful. Exception recovery requires identical complete readback.

`verify_installed_cohort` checks actual wheel/source/build receipts against a separately trusted manifest digest. Every execute rechecks hashes, RECORD/files, module origins, complete inventory, Python patch/platform. A prior receipt/version string is not proof, nor does the verifier secure a malicious process/filesystem. See [API](API.md) and [qualification](../qualification/README.md).

Runtime installation uses `--no-compile`; execution uses fresh `python -B`, no package bytecode caches and no alternate cache prefix. Build identities precede wheel construction; source/editable installs and unqualified layouts do not substitute. The [stored demo](../examples/stored_demo.py) uses original synthetic inputs and actual readback; browser inspection is distinct from HTML generation. Scenario parity supplements, rather than replaces, independent numerical fixtures.

## Compatibility and limits

CPython `>=3.12,<3.13`. Project cohort versions: `option-feature-contracts==0.1.0a1`, `option-features==0.1.0a1`, `option-feature-io==0.1.0a1`, `option-feature-workers==0.1.0a1`. Exact numerical/storage backends are `python-flint==0.9.0` and `duckdb==1.5.6`; individual package direct dependencies are listed in the [README](../README.md). This is a compatibility cohort, not a claim that every layer directly depends on every package. Exact source/wheel hashes, complete inventory, interpreter patch and platform require qualification. Alpha labels do not promise a stable API.

Only batch snapshots/replay of independent snapshots are admitted; no incremental update/restore/merge. Supplied spot introduces no unused equity dependency; equity packages never import options. Fixed count/byte/scalar/Decimal/range/solver ceilings apply and callers may lower them. There is no hard RSS guarantee, throughput claim, private-score parity, real/provider dataset acceptance or production-service qualification.

## Validation and publication

Remaining final evidence includes independently reviewed wire-identical fixtures, exact-source rebuilt wheels/sdists and clean installation on each supported platform, actual direct/batch/replay/stored semantic parity, resource/retry/cancellation/tamper checks, native-license inventory and an inspected stored-output browser demo. Windows and Linux require separate runs and canonical-output comparison. Source review and historical component checks do not replace final receipts. Local builds/tests provide merge evidence; hosted CI is optional.

Install only retained locally qualified wheels with reviewed hashes/platform locks. Controlled build identity is established before wheel creation, not inferred from a source install. Own code is [Apache-2.0](../LICENSE); dependencies/native components retain separate licenses/notices requiring artifact-specific inventory. No data rights are granted. Public registry/package publication retains owner approval.

[Implementation PR](https://github.com/atulsrivas1/option-feature-workers/pull/2), [R25 epic](https://github.com/atulsrivas1/equity-features/issues/526), [release page](https://github.com/atulsrivas1/option-feature-workers/releases), [version policy](VERSIONING.md).
