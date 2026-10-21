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
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import threading
import zipfile

from .types import Artifact, Cohort, CohortVerificationError

_PROJECTS = {
    "option-feature-contracts": ("contracts", "option_feature_contracts"),
    "option-features": ("calculations", "option_features"),
    "option-feature-io": ("io", "option_feature_io"),
    "option-feature-workers": ("workers", "option_feature_workers"),
}
_EXACT = {name: "0.1.0a1" for name in _PROJECTS}
_EXACT.update({"python-flint": "0.9.0", "duckdb": "1.5.6"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_LOCK = threading.RLock()
_CONFIGURED: dict[str, "_VerificationSetup"] = {}


@dataclass(frozen=True, slots=True)
class QualificationSource:
    distribution: str
    version: str
    source_commit: str
    wheel_sha256: str
    source_reference: str
    build_receipt_path: str
    build_receipt_sha256: str


@dataclass(frozen=True, slots=True)
class QualificationManifest:
    manifest_version: str
    artifacts: tuple[QualificationSource, ...]


@dataclass(frozen=True, slots=True)
class InstalledVerification:
    cohort_sha256: str
    worker_wheel_sha256: str
    qualification_manifest_sha256: str
    checked_files: int
    evidence_path: str


@dataclass(frozen=True, slots=True)
class _VerificationSetup:
    wheel_paths: tuple[str, ...]
    environment_receipt_path: str
    manifest: QualificationManifest
    trusted_manifest_sha256: str


def _fail(message: str) -> None:
    raise CohortVerificationError("unverified_cohort", message)


def _name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def qualification_manifest_digest(value: QualificationManifest) -> str:
    return sha256(b"option-qualification1\n" + _canonical(asdict(value))).hexdigest()


def _cohort_hash(cohort: Cohort) -> str:
    return sha256(b"option-cohort1\n" + _canonical(asdict(cohort))).hexdigest()


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


def _validate(cohort: Cohort, setup: _VerificationSetup | None = None) -> None:
    if type(cohort) is not Cohort or cohort.cohort_version != "option-cohort1":
        _fail("Wrong cohort version/type")
    if cohort.python_version != platform.python_version() or sys.version_info[:2] != (3, 12):
        _fail("Python differs from the qualified CPython 3.12 environment")
    if platform.python_implementation() != "CPython" or cohort.platform_id != sysconfig_platform():
        _fail("Platform or interpreter implementation differs from cohort")
    if sys.dont_write_bytecode is not True or sys.pycache_prefix is not None:
        _fail("Qualified execution requires python -B and no alternate pycache prefix")
    if type(cohort.artifacts) is not tuple or not cohort.artifacts or len(cohort.artifacts) > 256:
        _fail("Artifact inventory must be a bounded nonempty tuple")
    names = []
    for artifact in cohort.artifacts:
        if type(artifact) is not Artifact:
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
            _fail("Artifact role differs from fixed package ownership")
        if artifact.distribution in _EXACT and artifact.version != _EXACT[artifact.distribution]:
            _fail("Package version differs from the selected exact dependency")
        names.append(artifact.distribution)
    if names != sorted(set(names)) or not set(_EXACT).issubset(names):
        _fail("Inventory must be sorted, unique and include every project/backend package")
    if setup is None:
        return
    manifest = setup.manifest
    if (type(manifest) is not QualificationManifest
            or manifest.manifest_version != "option-qualification1"
            or type(manifest.artifacts) is not tuple
            or len(manifest.artifacts) != len(cohort.artifacts)):
        _fail("Wrong qualification manifest shape")
    for artifact, source in zip(cohort.artifacts, manifest.artifacts):
        if type(source) is not QualificationSource:
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
            or qualification_manifest_digest(manifest) != setup.trusted_manifest_sha256):
        _fail("Qualification manifest does not match the independently reviewed trust anchor")


def sysconfig_platform() -> str:
    """Exact platform ID used by the manifest; not a cross-platform assertion."""
    import sysconfig
    return sysconfig.get_platform()


def _source_receipt(source: QualificationSource) -> None:
    raw = _bounded_file(Path(source.build_receipt_path), 1048576)
    if sha256(raw).hexdigest() != source.build_receipt_sha256:
        _fail("Reviewed source/build receipt bytes changed")
    receipt = _strict_json(raw)
    required = {"receipt_version", "distribution", "version", "source_commit",
                "wheel_sha256", "source_reference", "evidence"}
    if type(receipt) is not dict or set(receipt) != required:
        _fail("Source/build receipt must use the exact qualification schema")
    if receipt["receipt_version"] != "option-source-build1":
        _fail("Unknown source/build receipt version")
    for field in ("distribution", "version", "source_commit", "wheel_sha256", "source_reference"):
        if receipt[field] != getattr(source, field):
            _fail("Source/build receipt is not bound to the actual artifact")
    if type(receipt["evidence"]) is not str or not receipt["evidence"]:
        _fail("Missing independently reviewed build/source evidence reference")


def _wheel_entries(path: Path, artifact: Artifact) -> dict[str, tuple[str, int]]:
    if _file_hash(path) != artifact.wheel_sha256:
        _fail("Wheel bytes differ from the reviewed artifact")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 100000:
            _fail("Wheel contains too many entries")
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
        return entries


def _check(cohort: Cohort, setup: _VerificationSetup) -> InstalledVerification:
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
    for artifact, source in zip(cohort.artifacts, setup.manifest.artifacts):
        _source_receipt(source)
        entries = _wheel_entries(paths[artifact.wheel_sha256], artifact)
        dist = installed[artifact.distribution]
        if dist.version != artifact.version or dist.files is None:
            _fail("Installed version/RECORD is unavailable or mismatched")
        installed_paths = {str(item).replace("\\", "/") for item in dist.files}
        installed_records = {str(item).replace("\\", "/"): item for item in dist.files}
        for name, (digest, size) in entries.items():
            if name not in installed_paths:
                _fail("Installed RECORD omits a reviewed wheel file")
            path = Path(dist.locate_file(name)).resolve(strict=True)
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
        roots = {PurePosixPath(name).parts[0] for name in entries if "/" in name
                 and not PurePosixPath(name).parts[0].endswith(".dist-info")}
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
    worker = next(item for item in cohort.artifacts if item.role == "workers")
    result = InstalledVerification(_cohort_hash(cohort), worker.wheel_sha256,
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
    evidence = {"receipt_version": "option-installed-verification1", **asdict(result),
                "python_version": platform.python_version(), "platform_id": sysconfig_platform(),
                "bytecode_profile": "python -B; no pycache prefix; installed package bytecode forbidden",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "module_origins": origins, "installed_inventory": sorted(installed),
                "limitation": "Coordinator-reviewed source/build manifest is the external trust root; this verifies local bytes, not numerical acceptance or reproducible-build provenance."}
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(_canonical(evidence) + b"\n")
    temporary.replace(output)
    return result


def verify_installed_cohort(cohort: Cohort, wheel_paths: tuple[str, ...],
                            environment_receipt_path: str,
                            qualification_manifest: QualificationManifest,
                            trusted_manifest_sha256: str) -> InstalledVerification:
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
                               qualification_manifest, trusted_manifest_sha256)
    with _LOCK:
        try:
            result = _check(cohort, setup)
        except CohortVerificationError:
            raise
        except Exception as exc:
            raise CohortVerificationError("unverified_cohort", "Installed verification failed") from exc
        _CONFIGURED[result.cohort_sha256] = setup
        return result


def require_verified_cohort(cohort: Cohort) -> InstalledVerification:
    """No cached pass: rehash all actual wheels and installed files each run."""
    with _LOCK:
        _validate(cohort)
        key = _cohort_hash(cohort)
        setup = _CONFIGURED.get(key)
        if setup is None:
            _fail("Cohort has no independently anchored installation-verification setup")
        try:
            return _check(cohort, setup)
        except CohortVerificationError:
            raise
        except Exception as exc:
            raise CohortVerificationError("unverified_cohort", "Installed evidence changed or became unavailable") from exc
