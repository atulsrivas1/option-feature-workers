# R25 workers contract preparation

## Current source-authoring checkpoint

Fresh coordinator-granted worker `/root/r25_worker_implementation` is authoring
EQ186 on `codex/r25-worker-implementation`, base
`73b1c5109d2ce5ff7273071c9a72ba8d87d4b5e1`, against independently reviewed contract
freeze `9403854ff37a7c0b5dbc57c142893a1ce0a262e4`. Candidate package, executor,
installed-cohort verifier, tests and synthetic integration/demo source now exist.
See [API](API.md) and [qualification](../qualification/README.md).
No runtime or build evidence exists. Original EQ142 resource hold remains in
force. The following preparation text is historical; the frozen option-owned
transport/executor choice now admits scoped source authoring, while actual
producer artifacts and integration remain mandatory runtime/merge gates.

Canonical EQ186; governance [GOV037 #581](https://github.com/atulsrivas1/equity-features/issues/581). Source-only preparation. Owner approved independent R25 progression: reviewed frozen R25 contracts, compatible interface choices and story readiness gate implementation; R18/EQ146 and EQ143/EQ144 acceptance are no longer blanket R25 prerequisites. R25 still owns its executor/resource, exact artifact, numerical and integrated qualification; none is claimed passed. See the [option contract draft](https://github.com/atulsrivas1/option-features/tree/codex/r25-contracts/docs/r25).

Own workers code only in this repository. The canonical contract owner is option-features; no independent amendment by a layer worker. Initial option package versions and dependency artifact locks are proposals, not built/released packages. Preserve source/contract/underlying identity, contracts versus shares, event/known-at, supplied/computed provenance and independently ready outputs.

Accepted legacy equity SDK/result/worker contracts are closed. Do not coerce option quantities to shares, collapse option/underlying identity, encode records in opaque fields, patch codec registries or assume a generic callback satisfies task/result admission. The shared-interface extension or option-owned transport/execution choice must be reviewed and frozen before worker implementation. EQ185 owns conversion/codec/storage; EQ186 owns bounded execution/retry/cancellation and serialized publication. Existing equity calculations and schemas remain unchanged.

The first integrated chain demo will compare direct pure results, worker results and stored readback, including unsupported/missing/future/partial cases; it is not implemented here. No datasets/DBs/tests/builds/benchmarks or service/registry operations were performed. Source-only documentation checks do not establish numerical or installed cross-platform qualification.
