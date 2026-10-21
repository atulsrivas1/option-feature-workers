"""Recheck installed artifacts, anchored to an externally reviewed manifest.

The expected manifest digest is a coordinator trust anchor, not a digest supplied
by an input-data producer. This module verifies local bytes; it does not prove
upstream authorship, mathematical correctness, or reproduce a build.
"""
import base64
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
import importlib.metadata as metadata
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import threading
import zipfile

from .types import FlowArtifact, FlowCohort, FlowCohortVerificationError

_PROJECTS = {
    "option-flow-contracts": ("contracts", "option_flow_contracts"),
    "option-flow-features": ("calculations", "option_flow_features"),
    "option-flow-io": ("io", "option_flow_io"),
    "option-flow-workers": ("workers", "option_flow_workers"),
}
_EXACT = {name: "0.1.0a1" for name in _PROJECTS}
_EXACT.update({"duckdb": "1.5.6"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_LOCK = threading.RLock()
_CONFIGURED: dict[str, "_VerificationSetup"] = {}


@dataclass(frozen=True, slots=True)
class FlowQualificationSource:
    distribution: str
    version: str
    source_commit: str
    wheel_sha256: str
    source_reference: str
    build_receipt_path: str
    build_receipt_sha256: str


@dataclass(frozen=True, slots=True)
class FlowQualificationManifest:
    manifest_version: str
    artifacts: tuple[FlowQualificationSource, ...]


@dataclass(frozen=True, slots=True)
class FlowInstalledVerification:
    cohort_sha256: str
    worker_wheel_sha256: str
    qualification_manifest_sha256: str
    checked_files: int
    evidence_path: str


@dataclass(frozen=True, slots=True)
class _VerificationSetup:
    wheel_paths: tuple[str, ...]
    environment_receipt_path: str
    manifest: FlowQualificationManifest
    trusted_manifest_sha256: str


def _fail(message: str) -> None:
    raise FlowCohortVerificationError("cohort_unverified", message)


def _name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def flow_qualification_manifest_digest(manifest: FlowQualificationManifest) -> str:
    return sha256(b"option-flow-qualification1\n" + _canonical(asdict(manifest))).hexdigest()


def _cohort_hash(cohort: FlowCohort) -> str:
    return sha256(b"option-flow-cohort1\n" + _canonical(asdict(cohort))).hexdigest()


def _bounded_file(path: Path, maximum: int) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
        _fail(f"Missing, linked or oversized evidence: {path.name}")
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        _fail("Evidence exceeded its byte bound")
    return value


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json(data: bytes) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail("Duplicate evidence JSON key")
            result[key] = value
        return result
    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: _fail("Nonfinite evidence token"))


def _validate(cohort: FlowCohort, setup: _VerificationSetup | None = None) -> None:
    if type(cohort) is not FlowCohort or cohort.cohort_version != "option-flow-cohort1":
        _fail("Wrong cohort version/type")
    if cohort.python_version != platform.python_version() or sys.version_info[:2] != (3, 12):
        _fail("Python differs from the qualified CPython 3.12 environment")
    if platform.python_implementation() != "CPython" or cohort.platform_id != sysconfig_platform():
        _fail("Platform or interpreter implementation differs from cohort")
    if sys.dont_write_bytecode is not True or sys.pycache_prefix is not None:
        _fail("Qualified execution requires python -B and no alternate pycache prefix")
    if type(cohort.artifacts) is not tuple or not cohort.artifacts or len(cohort.artifacts) > 256:
        _fail("FlowArtifact inventory must be a bounded nonempty tuple")
    names = []
    for artifact in cohort.artifacts:
        if type(artifact) is not FlowArtifact:
            _fail("Wrong artifact record")
        for value in (artifact.distribution, artifact.version, artifact.source_commit,
                      artifact.wheel_sha256, artifact.role):
            if type(value) is not str or not value or len(value) > 256:
                _fail("Invalid artifact scalar")
        if artifact.distribution != _name(artifact.distribution):
            _fail("Distribution names must be normalized")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", artifact.distribution):
            _fail("Invalid normalized distribution name")
        if not _COMMIT.fullmatch(artifact.source_commit) or not _HEX.fullmatch(artifact.wheel_sha256):
            _fail("Malformed artifact identity")
        expected_role = _PROJECTS.get(artifact.distribution, ("dependency", ""))[0]
        if artifact.role != expected_role:
            _fail("FlowArtifact role differs from fixed package ownership")
        if artifact.distribution in _EXACT and artifact.version != _EXACT[artifact.distribution]:
            _fail("Package version differs from the selected exact dependency")
        if artifact.distribution == "duckdb" and artifact.source_commit != "802a345bb627435d2a05d63cb74454fa98b60b5e":
            _fail("Native DuckDB upstream source differs from the admitted source")
        names.append(artifact.distribution)
    if names != sorted(set(names)) or set(names) != set(_EXACT):
        _fail("Inventory must be sorted, unique and include every project/backend package")
    if setup is None:
        return
    manifest = setup.manifest
    if (type(manifest) is not FlowQualificationManifest
            or manifest.manifest_version != "option-flow-qualification1"
            or type(manifest.artifacts) is not tuple
            or len(manifest.artifacts) != len(cohort.artifacts)):
        _fail("Wrong qualification manifest shape")
    for artifact, source in zip(cohort.artifacts, manifest.artifacts):
        if type(source) is not FlowQualificationSource:
            _fail("Wrong qualification source record")
        for value in asdict(source).values():
            if type(value) is not str or not value or len(value) > 4096:
                _fail("Invalid qualification source field")
        if (source.distribution, source.version, source.source_commit, source.wheel_sha256) != (
                artifact.distribution, artifact.version, artifact.source_commit, artifact.wheel_sha256):
            _fail("Source qualification differs from artifact cohort")
        if not _HEX.fullmatch(source.build_receipt_sha256):
            _fail("Invalid qualification receipt hash")
    if (type(setup.trusted_manifest_sha256) is not str
            or not _HEX.fullmatch(setup.trusted_manifest_sha256)
            or flow_qualification_manifest_digest(manifest) != setup.trusted_manifest_sha256):
        _fail("Qualification manifest does not match the independently reviewed trust anchor")


def sysconfig_platform() -> str:
    """Exact platform ID used by the manifest; not a cross-platform assertion."""
    import sysconfig
    return sysconfig.get_platform()


def _source_receipt(source: FlowQualificationSource) -> None:
    raw = _bounded_file(Path(source.build_receipt_path), 1048576)
    if sha256(raw).hexdigest() != source.build_receipt_sha256:
        _fail("Reviewed source/build receipt bytes changed")
    receipt = _strict_json(raw)
    required = {"receipt_version", "distribution", "version", "source_commit",
                "wheel_sha256", "source_reference", "evidence"}
    if type(receipt) is not dict or set(receipt) != required:
        _fail("Source/build receipt must use the exact qualification schema")
    if receipt["receipt_version"] != "option-flow-source-build1":
        _fail("Unknown source/build receipt version")
    for field in ("distribution", "version", "source_commit", "wheel_sha256", "source_reference"):
        if receipt[field] != getattr(source, field):
            _fail("Source/build receipt is not bound to the actual artifact")
    if type(receipt["evidence"]) is not str or not receipt["evidence"]:
        _fail("Missing independently reviewed build/source evidence reference")


def _wheel_entries(path: Path, artifact: FlowArtifact) -> dict[str, tuple[str, int]]:
    if _file_hash(path) != artifact.wheel_sha256:
        _fail("Wheel bytes differ from the reviewed artifact")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 100000:
            _fail("Wheel contains too many entries")
        for item in infos:
            if ((item.external_attr >> 16) & 0o170000) == 0o120000 or item.flag_bits & 1:
                _fail("Linked or encrypted wheel entries are not admitted")
            if item.file_size > 536870912:
                _fail("Wheel member exceeds verification bound")
        names = [item.filename for item in infos if not item.is_dir()]
        if len(names) != len(set(names)):
            _fail("Duplicate wheel entries")
        for name in names:
            part = PurePosixPath(name)
            if part.is_absolute() or ".." in part.parts or "\\" in name or ".data" in part.parts:
                _fail("Wheel path is not a supported pure install mapping")
            if any(p.endswith(".data") for p in part.parts):
                _fail("Wheel .data relocation requires a separately qualified mapping")
            if name.endswith((".pyc", ".pyo")):
                _fail("Bytecode-bearing wheels are not admitted by the source-only cache profile")
            if len(part.parts) == 1 and name.endswith(".py"):
                _fail("Standalone pure-module wheel layout requires a separately reviewed cache closure")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(metadata_names) != 1 or len(record_names) != 1:
            _fail("Wheel requires exactly one METADATA and RECORD")
        if any(archive.getinfo(name).file_size > 16777216 for name in metadata_names + record_names):
            _fail("Wheel metadata exceeds verification bound")
        info = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if _name(info["Name"]) != artifact.distribution or info["Version"] != artifact.version:
            _fail("Wheel metadata identity mismatch")
        records = {}
        for row in csv.reader(io.StringIO(archive.read(record_names[0]).decode("utf-8"))):
            if len(row) != 3 or row[0] in records:
                _fail("Malformed wheel RECORD")
            records[row[0]] = row[1:]
        if set(records) != set(names):
            _fail("Wheel RECORD does not cover its complete content")
        entries = {}
        for name in names:
            if name == record_names[0]:
                if records[name] != ["", ""]:
                    _fail("RECORD self-entry must be unhashed")
                continue
            info = archive.getinfo(name)
            if info.file_size > 536870912:
                _fail("Wheel entry exceeds qualification bound")
            digest = sha256()
            count = 0
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1048576), b""):
                    digest.update(chunk)
                    count += len(chunk)
            encoded = base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")
            if records[name] != ["sha256=" + encoded, str(count)]:
                _fail("Wheel RECORD hash or size mismatch")
            entries[name] = (digest.hexdigest(), count)
        if artifact.distribution in _PROJECTS:
            package = _PROJECTS[artifact.distribution][1]
            marker = f"{package}/_build_identity.json"
            if marker not in entries:
                _fail("Project wheel lacks a controlled-stage source marker")
            if _strict_json(archive.read(marker)) != {"source_commit": artifact.source_commit}:
                _fail("Project source marker differs from reviewed source/build receipt")
        if artifact.distribution == "duckdb":
            notices = [name for name in names if "license" in name.lower() or "notice" in name.lower()]
            if not notices or not any(archive.getinfo(name).file_size > 0 for name in notices):
                _fail("Native dependency wheel lacks bundled rights notices")
        return entries


def _module_inventory(entries, dist):
    """Closed importable source/extension descendants, without importing them."""
    modules = {}
    suffixes = sorted(set(importlib.machinery.EXTENSION_SUFFIXES + [".py"]), key=len, reverse=True)
    for name in entries:
        parts = list(PurePosixPath(name).parts)
        suffix = next((suffix for suffix in suffixes if parts[-1].endswith(suffix)), None)
        if suffix is None:
            continue
        stem = parts[-1][:-len(suffix)]
        package = stem == "__init__"
        components = parts[:-1] if package else parts[:-1] + [stem]
        if not components or not all(part.isidentifier() for part in components):
            continue
        # A path with non-package parents is not a declared descendant module.
        if any("/".join(components[:index]) + "/__init__.py" not in entries
               for index in range(1, len(components))):
            continue
        module = ".".join(components)
        origin = Path(dist.locate_file(name)).resolve(strict=True)
        if module in modules:
            _fail("Multiple wheel files claim one importable module")
        modules[module] = (origin, origin.parent if package else None)
    return modules


def _search_locations(actual, expected):
    if expected is None:
        if actual is not None:
            _fail("Nonpackage module gained package search locations")
        return
    if actual is None:
        _fail("Package lost its search locations")
    try:
        locations = tuple(actual)
        if len(locations) != 1 or type(locations[0]) is not str:
            _fail("Package search locations are not the closed wheel directory")
        original = Path(locations[0])
        if original.is_symlink() or original.resolve(strict=True) != expected:
            _fail("Package search path escapes the verified wheel directory")
    except FlowCohortVerificationError:
        raise
    except Exception as exc:
        raise FlowCohortVerificationError("cohort_unverified", "Invalid package search locations") from exc


def _verify_module_origins(modules):
    """Check actual loaded state and import resolution for every wheel descendant.

    Finding specs through the actual meta path mirrors Python resolution while
    supplying verified parent paths explicitly, so no unimported package executes.
    """
    origins = {}
    for name in sorted(modules, key=lambda value:(value.count("."), value)):
        expected, package_dir = modules[name]
        if name in sys.modules:
            loaded = sys.modules[name]
            if loaded is None:
                _fail("Runtime module is blocked by a null sys.modules entry")
            loaded_file = getattr(loaded, "__file__", None)
            loaded_spec = getattr(loaded, "__spec__", None)
            if (type(loaded_file) is not str or Path(loaded_file).resolve() != expected
                    or loaded_spec is None or type(loaded_spec.origin) is not str
                    or Path(loaded_spec.origin).resolve() != expected):
                _fail("Loaded descendant module origin differs from verified wheel")
            _search_locations(getattr(loaded_spec, "submodule_search_locations", None), package_dir)
            _search_locations(getattr(loaded, "__path__", None), package_dir)
        parent = name.rpartition(".")[0]
        parent_path = None if not parent else [str(modules[parent][1])]
        spec = None
        for finder in tuple(sys.meta_path):
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                _fail("Legacy import finder is outside the qualified import profile")
            spec = find_spec(name, parent_path, None)
            if spec is not None:
                break
        if spec is None or type(spec.origin) is not str or Path(spec.origin).resolve() != expected:
            _fail("Importable descendant module origin differs from verified wheel")
        _search_locations(spec.submodule_search_locations, package_dir)
        origins[name] = str(expected)
    for name in tuple(sys.modules):
        if any(name.startswith(root + ".") for root in modules if "." not in root) and name not in modules:
            _fail("Loaded undeclared descendant module")
    return origins


def _check(cohort: FlowCohort, setup: _VerificationSetup) -> FlowInstalledVerification:
    _validate(cohort, setup)
    paths = {}
    for name in setup.wheel_paths:
        path = Path(name).resolve(strict=True)
        if path.suffix != ".whl" or not path.is_file() or path.stat().st_size > 536870912:
            _fail("Wheel path must name an actual wheel")
        digest = _file_hash(path)
        if digest in paths:
            _fail("Duplicate wheel artifact")
        paths[digest] = path
    if set(paths) != {item.wheel_sha256 for item in cohort.artifacts}:
        _fail("Wheel inventory differs from complete cohort")
    installed = {}
    for dist in metadata.distributions():
        name = _name(dist.metadata["Name"])
        if name in installed:
            _fail("Duplicate installed distribution")
        installed[name] = dist
    if set(installed) != {item.distribution for item in cohort.artifacts}:
        _fail("Entire installed distribution inventory must match reviewed cohort")
    checked = 0
    origins = {}
    all_entries = set()
    for artifact, source in zip(cohort.artifacts, setup.manifest.artifacts):
        _source_receipt(source)
        entries = _wheel_entries(paths[artifact.wheel_sha256], artifact)
        all_entries.update(entries)
        dist = installed[artifact.distribution]
        if dist.version != artifact.version or dist.files is None:
            _fail("Installed version/RECORD is unavailable or mismatched")
        installed_paths = {str(item).replace("\\", "/") for item in dist.files}
        if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
               for name in installed_paths):
            _fail("Installed RECORD contains a relocated path")
        installed_records = {str(item).replace("\\", "/"): item for item in dist.files}
        for name, (digest, size) in entries.items():
            if name not in installed_paths:
                _fail("Installed RECORD omits a reviewed wheel file")
            original = Path(dist.locate_file(name))
            if original.is_symlink() or any(parent.is_symlink() for parent in original.parents):
                _fail("Installed file or ancestor is linked")
            path = original.resolve(strict=True)
            if not path.is_file() or path.stat().st_size != size or _file_hash(path) != digest:
                _fail("Installed file differs from reviewed wheel")
            record = installed_records[name]
            expected_hash = base64.urlsafe_b64encode(bytes.fromhex(digest)).rstrip(b"=").decode("ascii")
            if (record.hash is None or record.hash.mode != "sha256"
                    or record.hash.value != expected_hash or record.size != size):
                _fail("Installed RECORD hash/size differs from wheel content")
            checked += 1
        # Only non-executable installer metadata may be added. Bytecode is
        # executable content and is never silently exempted from qualification.
        for name in installed_paths - set(entries):
            if (name.endswith(".dist-info/RECORD") or name.endswith(".dist-info/INSTALLER")
                    or name.endswith(".dist-info/REQUESTED") or name.endswith(".dist-info/direct_url.json")):
                continue
            _fail("Installed RECORD contains an unqualified additional file")
        roots = {PurePosixPath(name).parts[0] for name in entries if "/" in name}
        for root_name in roots:
            root_path = Path(dist.locate_file(root_name))
            if root_path.is_symlink():
                _fail("Installed package root is a symlink")
            for path in root_path.rglob("*"):
                if path.is_symlink():
                    _fail("Installed package contains a symlink")
                if not path.is_file():
                    continue
                relative = root_name + "/" + path.relative_to(root_path).as_posix()
                if relative not in entries:
                    bookkeeping = root_name.endswith(".dist-info") and path.name in (
                        "RECORD", "INSTALLER", "REQUESTED", "direct_url.json") and path.parent == root_path
                    if not bookkeeping:
                        _fail("Installed package contains unrecorded extra content")
        if artifact.distribution in _PROJECTS:
            package = _PROJECTS[artifact.distribution][1]
            expected = Path(dist.locate_file(f"{package}/__init__.py")).resolve(strict=True)
            spec = importlib.util.find_spec(package)
            if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected:
                _fail("Project module origin is shadowed outside the verified wheel")
            loaded = sys.modules.get(package)
            if loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() != expected:
                _fail("Loaded project module origin differs from installed artifact")
            origins[package] = str(expected)
        # Verify top-level import origins for native dependencies as well as
        # project packages. Do not import or execute modules for this check.
        module_names = set()
        for name in entries:
            parts = PurePosixPath(name).parts
            if len(parts) > 1 and parts[1] == "__init__.py" and "." not in parts[0]:
                module_names.add(parts[0])
            elif len(parts) == 1 and name.endswith((".py", ".pyd", ".so")):
                module_names.add(name.split(".")[0])
        for module in module_names:
            spec = importlib.util.find_spec(module)
            if spec is None or spec.origin is None:
                _fail("Installed runtime module has no verifiable origin")
            actual_origin = Path(spec.origin).resolve(strict=True)
            matching_paths = {Path(dist.locate_file(name)).resolve() for name in entries
                              if name == f"{module}.py" or name.startswith(f"{module}/")
                              or ("/" not in name and name.split(".")[0] == module)}
            if actual_origin not in matching_paths:
                _fail("Runtime module is shadowed outside the qualified wheel")
            # Top-level native extensions remain supported (notably _duckdb).
            # Their adjacent caches must not become unchecked executable content.
            installed_root = Path(dist.locate_file(""))
            adjacent = (installed_root / (module + ".pyc"), installed_root / (module + ".pyo"))
            cached = tuple((installed_root / "__pycache__").glob(module + ".*.pyc"))
            cached += tuple((installed_root / "__pycache__").glob(module + ".*.pyo"))
            if any(path.exists() for path in adjacent + cached):
                _fail("Runtime module has unqualified adjacent executable bytecode")
            loaded = sys.modules.get(module)
            if loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() != actual_origin:
                _fail("Loaded runtime module differs from verified origin")
            origins[module] = str(actual_origin)
        origins.update(_verify_module_origins(_module_inventory(entries, dist)))
    # Top-level source/native files have no package directory to recurse into.
    # Reject executable files outside all selected wheel inventories.
    installed_roots = {Path(dist.locate_file("")).resolve() for dist in installed.values()}
    for root in installed_roots:
        for path in root.iterdir():
            if path.is_file() and path.name.endswith((".py", ".pyc", ".pyo", ".pyd", ".so")):
                if path.name not in all_entries:
                    _fail("Unqualified top-level executable content")
    worker = next(item for item in cohort.artifacts if item.role == "workers")
    result = FlowInstalledVerification(_cohort_hash(cohort), worker.wheel_sha256,
                                   setup.trusted_manifest_sha256, checked,
                                   setup.environment_receipt_path)
    output = Path(setup.environment_receipt_path)
    output_resolved = output.resolve()
    protected_paths = set(paths.values()) | {Path(source.build_receipt_path).resolve()
                                            for source in setup.manifest.artifacts}
    if output_resolved in protected_paths or output.suffix != ".json":
        _fail("Verification output cannot overwrite artifact/source evidence")
    for dist in installed.values():
        root = Path(dist.locate_file("")).resolve()
        if output_resolved.is_relative_to(root):
            _fail("Verification output must live outside installed distribution roots")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"receipt_version": "option-flow-installed-verification1", **asdict(result),
                "python_version": platform.python_version(), "platform_id": sysconfig_platform(),
                "bytecode_profile": "python -B; no pycache prefix; installed package bytecode forbidden",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "module_origins": origins, "installed_inventory": sorted(installed),
                "limitation": "Coordinator-reviewed source/build manifest is the external trust root; this verifies local bytes, not numerical acceptance or reproducible-build provenance."}
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(_canonical(evidence) + b"\n")
    temporary.replace(output)
    return result


def verify_flow_installed(cohort: FlowCohort, wheel_paths: tuple[str, ...],
                            environment_receipt_path: str,
                            manifest: FlowQualificationManifest,
                            trusted_manifest_sha256: str) -> FlowInstalledVerification:
    """Configure evidence locations and verify now; execute repeats every check.

    ``trusted_manifest_sha256`` MUST be obtained from independent coordinator
    source/artifact review. Taking it from a producer's own inputs defeats that
    trust boundary. The environment receipt is generated output, never an input
    assertion that a prior check passed.
    """
    if (type(wheel_paths) is not tuple or len(wheel_paths) > 256
            or any(type(path) is not str or not path or len(path) > 4096 for path in wheel_paths)
            or type(environment_receipt_path) is not str or not environment_receipt_path
            or len(environment_receipt_path) > 4096):
        _fail("Invalid verification setup")
    setup = _VerificationSetup(wheel_paths, environment_receipt_path,
                               manifest, trusted_manifest_sha256)
    with _LOCK:
        try:
            result = _check(cohort, setup)
        except FlowCohortVerificationError:
            raise
        except Exception as exc:
            raise FlowCohortVerificationError("cohort_unverified", "Installed verification failed") from exc
        _CONFIGURED[result.cohort_sha256] = setup
        return result


def require_verified_flow_cohort(cohort: FlowCohort) -> FlowInstalledVerification:
    """No cached pass: rehash all actual wheels and installed files each run."""
    with _LOCK:
        _validate(cohort)
        key = _cohort_hash(cohort)
        setup = _CONFIGURED.get(key)
        if setup is None:
            _fail("FlowCohort has no independently anchored installation-verification setup")
        try:
            return _check(cohort, setup)
        except Exception as exc:
            raise FlowCohortVerificationError("cohort_changed", "Installed evidence changed or became unavailable") from exc
