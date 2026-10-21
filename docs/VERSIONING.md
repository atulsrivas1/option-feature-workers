# Version and compatibility policy

Owner agreed independent library/package versions with tested cross-repository compatibility on October 20, 2026. R25 is a delivery milestone, not a package version. Candidate option package versions have not been built, installed or published by this baseline.

Experimental dependencies are exact pins, extended to artifact hashes/source commits in release locks. Do not follow a moving equity branch or upgrade automatically. First qualify the selected package combination and shared-contract agreement on Windows/Linux, update the compatibility manifest and then release the consuming package. A changed exact dependency requires a new immutable consuming-package release; do not overwrite released metadata.

Once stable APIs are established: compatible fixes increment patch, compatible additions minor, and breaking public API/schema/calculation contracts major. Before 1.0, compatibility must be explicit; do not assume a minor/patch is safe. Numerical corrections include independent validation, change notes and algorithm/method identity where semantics change.

Track package version, canonical schema version, formula/model/config version and data/run provenance separately. Immutable run manifests bind exact transitive packages/artifacts, method/configuration, source revisions, input clocks/basis/coverage and result schema. A version string is not an artifact checksum or proof of numerical compatibility.

Dependencies are one-way and selected by capability: shared equity contracts/calculations -> option contracts/calculations -> strategy consumers; I/O and workers consume pure contracts rather than reverse that relationship. Existing accepted equity a4 and I/O/worker source pins are references pending explicit option compatibility qualification. Active EF1 candidate versions are not accepted replacements.

Primary standards: [Python packaging versions](https://packaging.python.org/en/latest/discussions/versioning/) and [Semantic Versioning](https://semver.org/). This project uses Python-compatible alpha labels during experimentation and stable semantic-version rules after declared stabilization. No package registry name or publication availability is established here.
