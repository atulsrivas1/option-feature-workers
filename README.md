# option-feature-workers

Bounded option execution and orchestration. Compose selected option calculations with explicit adapters/sinks, bounded resources, deterministic retry/cancellation and serialized publication. Existing equity task admission/dispatch is not generic option support.

Status: [EQ186](https://github.com/atulsrivas1/equity-features/issues/531) source authoring in progress against independently reviewed option contract commit `9403854ff37a7c0b5dbc57c142893a1ce0a262e4`. The candidate `packages/workers` distribution is `option-feature-workers==0.1.0a1`. It has not been built, installed, executed or accepted. The original EQ142 protected runtime hold remains in force. Canonical [R25/E33](https://github.com/atulsrivas1/equity-features/issues/526) retains all numbered stories; actual producer integration and release gates remain open.

See the [public API and verification trust boundary](docs/API.md) and [qualification plan](qualification/README.md). The source candidate provides sequential batch/replay, actual-input logical admission, content-bound work, mandatory installed-artifact verification and separate atomic sink publication/readback. Original synthetic demo inputs and local stored-output HTML source live in `examples`; they have not run and contain no private/provider data. No numerical formula is implemented here.

See [work agreements](AGENTS.md), [version policy](docs/VERSIONING.md) and [handoff](docs/SESSION_HANDOFF.md). Existing equity inputs/results/codecs/workers are closed contracts, not generic option extension promises. R25 must qualify option units, identity/provenance and new interface boundaries before runtime authoring.

Licensed under [Apache-2.0](LICENSE). Code licensing grants no provider-data or private-source rights.
