# R25 workers contract preparation

Canonical EQ186; governance [GOV037 #581](https://github.com/atulsrivas1/equity-features/issues/581). Source-only preparation; EQ146 and reviewed contracts block implementation. See the [option contract draft](https://github.com/atulsrivas1/option-features/tree/codex/r25-contracts/docs/r25).

Own workers code only in this repository. The canonical contract owner is option-features; no independent amendment by a layer worker. Initial option package versions and dependency artifact locks are proposals, not built/released packages. Preserve source/contract/underlying identity, contracts versus shares, event/known-at, supplied/computed provenance and independently ready outputs.

Accepted legacy equity SDK/result/worker contracts are closed. Do not coerce option quantities to shares, collapse option/underlying identity, encode records in opaque fields, patch codec registries or assume a generic callback satisfies task/result admission. The shared-interface extension or option-owned transport/execution choice must be reviewed and frozen before worker implementation. EQ185 owns conversion/codec/storage; EQ186 owns bounded execution/retry/cancellation and serialized publication. Existing equity calculations and schemas remain unchanged.

The first integrated chain demo will compare direct pure results, worker results and stored readback, including unsupported/missing/future/partial cases; it is not implemented here. No datasets/DBs/tests/builds/benchmarks or service/registry operations were performed. Source-only documentation checks do not establish numerical or installed cross-platform qualification.
