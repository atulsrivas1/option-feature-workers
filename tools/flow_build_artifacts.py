"""Build unqualified R26 artifact candidates from explicit immutable Git commits.

Run under a separate coordinator build lease. This tool has no authority to
install, verify, admit, publish, or access networks. Only private staging changes.
"""
import argparse
from email.parser import BytesParser
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tomllib
import traceback
import zipfile

PACKAGES = (
    ("library", "option-features", "packages/flow-contracts", "option-flow-contracts", "option_flow_contracts", "contracts", ()),
    ("library", "option-features", "packages/flow-features", "option-flow-features", "option_flow_features", "calculations", ("option-flow-contracts==0.1.0a1",)),
    ("io", "option-feature-io", "packages/flow-io", "option-flow-io", "option_flow_io", "io", ("option-flow-contracts==0.1.0a1", "duckdb==1.5.6")),
    ("workers", "option-feature-workers", "packages/flow-workers", "option-flow-workers", "option_flow_workers", "workers", ("option-flow-contracts==0.1.0a1", "option-flow-features==0.1.0a1", "option-flow-io==0.1.0a1")),
)
NATIVE_COMMIT = "802a345bb627435d2a05d63cb74454fa98b60b5e"
MAX_ARCHIVE_BYTES = 268435456


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(path):
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def inventory(root):
    return {path.relative_to(root).as_posix():digest(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def safe_extract(archive, destination):
    """No tar extraction helpers: reject links/devices/traversal before writes."""
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve(strict=True)
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        if len(members) > 100000:
            raise ValueError("Archive member count exceeds bound")
        names, total, selected = set(), 0, []
        reserved = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.IGNORECASE)
        for member in members:
            parts = PurePosixPath(member.name)
            if (parts.is_absolute() or not member.name or ".." in parts.parts
                    or "\\" in member.name or ":" in member.name
                    or any(part.rstrip(". ") != part for part in parts.parts)
                    or any(reserved.fullmatch(part) for part in parts.parts)
                    or parts.as_posix() in names or not (member.isdir() or member.isfile())):
                raise ValueError("Unsafe, duplicate, linked or nonregular archive member")
            names.add(parts.as_posix())
            target = root.joinpath(*parts.parts)
            if not target.resolve().is_relative_to(root):
                raise ValueError("Archive target escapes staging")
            total += member.size
            if total > MAX_ARCHIVE_BYTES or member.size < 0:
                raise ValueError("Archive exceeds expanded byte bound")
            selected.append((member, target))
        for member, target in selected:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=1048576)
    return root


class Commands:
    def __init__(self, output, environment):
        self.output, self.environment, self.records = output, environment, []

    def run(self, arguments, *, cwd, binary_output=None):
        ordinal = len(self.records)
        logfile = self.output / f"command-{ordinal:03d}.log"
        record = {"argv":[str(value) for value in arguments], "cwd":str(cwd), "log":str(logfile), "exit_code":None}
        self.records.append(record)
        # Persist attempts even if process creation fails or an interrupt arrives.
        write_new(self.output / f"command-{ordinal:03d}.json", record)
        try:
            if binary_output is None:
                result = subprocess.run(arguments, cwd=cwd, env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                logfile.write_bytes(result.stdout)
            else:
                with binary_output.open("xb") as stream:
                    result = subprocess.run(arguments, cwd=cwd, env=self.environment, stdout=stream, stderr=subprocess.PIPE, check=False)
                logfile.write_bytes(result.stderr)
            record["exit_code"] = result.returncode
            if result.returncode:
                raise RuntimeError(f"Command failed ({result.returncode}); see {logfile}")
            return result.stdout if binary_output is None else None
        finally:
            # A separate completion record preserves original attempted command.
            write_new(self.output / f"command-{ordinal:03d}-completion.json", record)


def wheel_inventory(path, distribution, version, marker=None):
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len({info.filename for info in infos}) != len(infos):
            raise ValueError("Duplicate wheel entries")
        total = 0
        for info in infos:
            part = PurePosixPath(info.filename)
            total += info.file_size
            if (part.is_absolute() or ".." in part.parts or "\\" in info.filename
                    or ":" in info.filename or ((info.external_attr >> 16) & 0o170000) == 0o120000
                    or info.flag_bits & 1 or total > 1073741824):
                raise ValueError("Unsafe or oversized wheel member")
        metadata = [info.filename for info in infos if info.filename.endswith(".dist-info/METADATA")]
        if len(metadata) != 1 or archive.getinfo(metadata[0]).file_size > 1048576:
            raise ValueError("Wheel needs one bounded METADATA")
        parsed = BytesParser().parsebytes(archive.read(metadata[0]))
        normalized = re.sub(r"[-_.]+", "-", parsed["Name"]).lower()
        if (normalized, parsed["Version"]) != (distribution, version):
            raise ValueError("Actual wheel metadata differs from selected identity")
        content = {}
        notices = {}
        for info in infos:
            hashed = sha256()
            with archive.open(info) as stream:
                for block in iter(lambda:stream.read(1048576), b""):
                    hashed.update(block)
            content[info.filename] = {"sha256":hashed.hexdigest(), "bytes":info.file_size}
            if "license" in info.filename.lower() or "notice" in info.filename.lower():
                notices[info.filename] = content[info.filename]
        if marker is not None:
            name, commit = marker
            if json.loads(archive.read(f"{name}/_build_identity.json")) != {"source_commit":commit}:
                raise ValueError("Built source marker does not match archived commit")
        return {"content":content, "notices":notices, "metadata":{"name":normalized,
                "version":parsed["Version"], "requires_dist":parsed.get_all("Requires-Dist", []),
                "requires_python":parsed.get("Requires-Python")}}


def only(directory, pattern):
    values = list(directory.glob(pattern))
    if len(values) != 1:
        raise ValueError(f"Expected one {pattern} in {directory}; found {len(values)}")
    return values[0].resolve(strict=True)


def receipt(output, distribution, version, commit, wheel, source_reference, evidence):
    path = output / (distribution + ".json")
    write_new(path, {"receipt_version":"option-flow-source-build1", "distribution":distribution,
        "version":version, "source_commit":commit, "wheel_sha256":digest(wheel),
        "source_reference":source_reference, "evidence":str(evidence)})
    return path.resolve(strict=True)


def execute(args):
    output = args.output.absolute()
    repositories = {name:getattr(args, name + "_repo").resolve(strict=True) for name in ("library", "io", "workers")}
    commits = {name:getattr(args, name + "_commit") for name in repositories}
    for name, repo in repositories.items():
        if not re.fullmatch("[0-9a-f]{40}", commits[name]):
            raise ValueError("Explicit immutable 40-lowercase-hex commits required")
        if output.resolve().is_relative_to(repo):
            raise ValueError("Output staging must be outside all source repositories")
    if any(parent.is_symlink() for parent in [output.parent, *output.parents]):
        raise ValueError("Output staging ancestors must not be links")
    output.mkdir(parents=False, exist_ok=False)
    environment = os.environ.copy()
    environment.update(PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1",
                       PYTHONNOUSERSITE="1", PIP_CONFIG_FILE=os.devnull)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    commands = Commands(output, environment)
    summary = {"schema_version":"option-flow-artifact-build-attempt1", "qualified":False,
               "authorized":False, "completed":False, "commands":commands.records,
               "source_commits":commits, "limitation":"Local artifact construction only; independent source/artifact review, runtime admission, platform qualification and release approval remain separate."}
    try:
        builder = args.builder_python.resolve(strict=True)
        inspection = commands.run([str(builder), "-I", "-B", "-c", "import importlib.metadata as m,json,platform,sys,sysconfig; print(json.dumps({'python':sys.version,'implementation':platform.python_implementation(),'platform_id':sysconfig.get_platform(),'setuptools':m.version('setuptools'),'build':m.version('build'),'wheel':m.version('wheel'),'packaging':m.version('packaging')}))"], cwd=output)
        versions = json.loads(inspection)
        if versions["setuptools"] != "80.9.0" or versions["implementation"] != "CPython" or not versions["python"].startswith("3.12."):
            raise ValueError("Prepared CPython3.12 builder with exact setuptools80.9.0 required")
        if versions["platform_id"] not in ("win-amd64", "linux-x86_64"):
            raise ValueError("Unselected platform")
        summary["builder"] = versions
        native = args.duckdb_wheel.resolve(strict=True)
        native_input_sha256 = digest(native)
        native_info = wheel_inventory(native, "duckdb", "1.5.6")
        if not native_info["notices"]:
            raise ValueError("DuckDB wheel must retain actual bundled license/notices")
        tag_check = commands.run([str(builder), "-I", "-B", "-c", "import json,sys; from packaging.utils import parse_wheel_filename; from packaging.tags import sys_tags; name,version,build,tags=parse_wheel_filename(sys.argv[1]); print(json.dumps({'compatible':bool(set(tags)&set(sys_tags())),'tags':sorted(map(str,tags))}))", native.name], cwd=output)
        native_tags = json.loads(tag_check)
        if not native_tags["compatible"]:
            raise ValueError("DuckDB wheel does not match the actual builder platform/interpreter")
        native_dir = output / "native"
        native_dir.mkdir()
        native_copy = native_dir / native.name
        with native.open("rb") as incoming, native_copy.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        if digest(native_copy) != native_input_sha256 or digest(native) != native_input_sha256:
            raise ValueError("Externally supplied DuckDB wheel changed during inspection/copy")
        native_detail = native_dir / "provenance.json"
        write_new(native_detail, {"distribution":"duckdb", "version":"1.5.6", "upstream_source_commit":NATIVE_COMMIT,
            "upstream_source_reference":"https://github.com/duckdb/duckdb/tree/" + NATIVE_COMMIT,
            "upstream_native_reproducible_build_claim":False,
            "source_of_local_input":"Externally supplied wheel; no upstream authorship/rebuild proof inferred",
            "input_path":str(native), "input_sha256":native_input_sha256, "copied_sha256":digest(native_copy),
            "actual_wheel":native_info, "actual_compatible_tags":native_tags})
        receipts = output / "receipts"
        receipts.mkdir()
        native_receipts = receipts / "native"
        native_receipts.mkdir()
        native_reference = "https://github.com/duckdb/duckdb/tree/" + NATIVE_COMMIT
        native_receipt = receipt(native_receipts, "duckdb", "1.5.6", NATIVE_COMMIT, native_copy, native_reference, native_detail)
        forms = {"original_wheel":[], "original_sdist_rebuilt_wheel":[]}
        parity = {}
        for key, repository_name, package_path, distribution, module, role, dependencies in PACKAGES:
            repo, commit = repositories[key], commits[key]
            actual = commands.run(["git", "-C", str(repo), "rev-parse", commit + "^{commit}"], cwd=output).decode("ascii").strip()
            if actual != commit:
                raise ValueError("Resolved Git source differs from explicit selected commit")
            item = output / distribution
            item.mkdir()
            archive = item / "source.tar"
            commands.run(["git", "-C", str(repo), "archive", "--format=tar", commit, "--", package_path], cwd=output, binary_output=archive)
            staged = safe_extract(archive, item / "source")
            package = staged / package_path
            before = inventory(staged)
            manifest = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))
            if manifest["build-system"] != {"requires":["setuptools==80.9.0"], "build-backend":"setuptools.build_meta"}:
                raise ValueError("Only exact reviewed build backend is admitted")
            project = manifest["project"]
            if (project["name"], project["version"], tuple(project.get("dependencies", []))) != (distribution, "0.1.0a1", dependencies):
                raise ValueError("Staged package identity/dependencies differ from closed profile")
            marker = package / "src" / module / "_build_identity.json"
            # The sole intentional source overlay is private staged source identity.
            marker.write_bytes(canonical({"source_commit":commit}) + b"\n")
            after = inventory(staged)
            changed = [name for name in set(before) | set(after) if before.get(name) != after.get(name)]
            expected_marker = marker.relative_to(staged).as_posix()
            if changed != [expected_marker]:
                raise ValueError("Staged overlay changed more than the build marker")
            source_detail = item / "source-inventory.json"
            write_new(source_detail, {"archive_sha256":digest(archive), "archive_bytes":archive.stat().st_size,
                       "git_commit":commit, "package_whitelist_path":package_path,
                       "archived_files_sha256":before, "staged_files_sha256":after,
                       "sole_overlay":expected_marker})
            original_dir = item / "original"
            commands.run([str(builder), "-I", "-B", "-m", "build", "--no-isolation", "--wheel", "--sdist", "--outdir", str(original_dir), str(package)], cwd=output)
            original = only(original_dir, "*.whl")
            sdist = only(original_dir, "*.tar.gz")
            original_info = wheel_inventory(original, distribution, "0.1.0a1", (module, commit))
            rebuilt_root = safe_extract(sdist, item / "sdist-source")
            candidates = list(rebuilt_root.glob("*/pyproject.toml"))
            if len(candidates) != 1:
                raise ValueError("Original sdist must contain exactly one package root")
            rebuilt_dir = item / "rebuilt"
            commands.run([str(builder), "-I", "-B", "-m", "build", "--no-isolation", "--wheel", "--outdir", str(rebuilt_dir), str(candidates[0].parent)], cwd=output)
            rebuilt = only(rebuilt_dir, "*.whl")
            rebuilt_info = wheel_inventory(rebuilt, distribution, "0.1.0a1", (module, commit))
            comparison = {"original_wheel_sha256":digest(original), "original_sdist_sha256":digest(sdist),
                "rebuilt_wheel_sha256":digest(rebuilt), "same_archive_bytes":digest(original)==digest(rebuilt),
                "same_complete_wheel_member_bytes":original_info["content"]==rebuilt_info["content"],
                "source_inventory":str(source_detail), "original_wheel":original_info, "rebuilt_wheel":rebuilt_info}
            detail = item / "build-evidence.json"
            write_new(detail, comparison)
            parity[distribution] = comparison
            source_reference = f"https://github.com/atulsrivas1/{repository_name}/tree/{commit}"
            for form, wheel in (("original_wheel", original), ("original_sdist_rebuilt_wheel", rebuilt)):
                form_receipts = receipts / form
                form_receipts.mkdir(exist_ok=True)
                build_receipt = receipt(form_receipts, distribution, "0.1.0a1", commit, wheel, source_reference, detail)
                forms[form].append({"distribution":distribution, "version":"0.1.0a1", "role":role,
                    "source_commit":commit, "wheel_path":str(wheel), "source_reference":source_reference,
                    "build_receipt_path":str(build_receipt)})
        for form, entries in forms.items():
            entries.append({"distribution":"duckdb", "version":"1.5.6", "role":"dependency", "source_commit":NATIVE_COMMIT,
                "wheel_path":str(native_copy.resolve()), "source_reference":native_reference, "build_receipt_path":str(native_receipt)})
            write_new(output / (form + "-candidate-lock-inputs.json"), sorted(entries, key=lambda item:item["distribution"]))
        summary.update(completed=True, artifact_forms=list(forms), parity=parity)
    except BaseException as exc:
        summary["failure"] = {"type":type(exc).__name__, "message":str(exc), "traceback":traceback.format_exc()}
        raise
    finally:
        write_new(output / "build-attempt.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("library", "io", "workers"):
        parser.add_argument("--" + name + "-repo", required=True, type=Path)
        parser.add_argument("--" + name + "-commit", required=True)
    parser.add_argument("--builder-python", required=True, type=Path)
    parser.add_argument("--duckdb-wheel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    execute(parser.parse_args())

if __name__ == "__main__":
    main()
