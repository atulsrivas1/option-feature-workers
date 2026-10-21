"""Prepare a candidate artifact lock from actual files; never self-authorizes it.

Run only after independently reviewed exact-source builds. The printed digest is
an output for external coordinator review, not authority to execute this lock.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import zipfile

INVENTORY = {"option-flow-contracts":("0.1.0a1","contracts"),
             "option-flow-features":("0.1.0a1","calculations"),
             "option-flow-io":("0.1.0a1","io"),
             "option-flow-workers":("0.1.0a1","workers"), "duckdb":("1.5.6","dependency")}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")

def filehash(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, help="Five-item JSON list: distribution/version/role/source_commit/wheel_path/source_reference/build_receipt_path")
    parser.add_argument("output", type=Path, help="New candidate manifest path; existing output is never overwritten")
    args = parser.parse_args()
    values = json.loads(args.inputs.read_text(encoding="utf-8"))
    expected_keys = {"distribution", "version", "role", "source_commit", "wheel_path", "source_reference", "build_receipt_path"}
    if type(values) is not list or len(values) != 5:
        raise ValueError("Exactly five artifact entries required")
    names = []
    sources = []
    artifacts = []
    for value in sorted(values, key=lambda item:item["distribution"]):
        if type(value) is not dict or set(value) != expected_keys or any(type(v) is not str or not v for v in value.values()):
            raise ValueError("Wrong closed input shape")
        name = value["distribution"]
        if name not in INVENTORY or (value["version"], value["role"]) != INVENTORY[name]:
            raise ValueError("Artifact inventory/version/role mismatch")
        if re.fullmatch("[0-9a-f]{40}", value["source_commit"]) is None:
            raise ValueError("Actual source commit must be 40 lowercase hexadecimal characters")
        wheel = Path(value["wheel_path"]).resolve(strict=True)
        receipt = Path(value["build_receipt_path"]).resolve(strict=True)
        if wheel.suffix != ".whl" or not zipfile.is_zipfile(wheel):
            raise ValueError("Actual wheel archive required")
        digest = filehash(wheel)
        source = {key:value[key] for key in ("distribution", "version", "source_commit", "source_reference")}
        source.update(wheel_sha256=digest, build_receipt_path=str(receipt), build_receipt_sha256=filehash(receipt))
        build = json.loads(receipt.read_text(encoding="utf-8"))
        if type(build) is not dict or build.get("receipt_version") != "option-flow-source-build1":
            raise ValueError("Actual reviewed flow build receipt required")
        if any(build.get(key) != source[key] for key in ("distribution", "version", "source_commit", "wheel_sha256", "source_reference")):
            raise ValueError("Source/build receipt differs from artifact")
        sources.append(source)
        artifacts.append({key:source[key] for key in ("distribution", "version", "source_commit", "wheel_sha256")} | {"role":value["role"]})
        names.append(name)
    if set(names) != set(INVENTORY) or len(set(names)) != 5:
        raise ValueError("Exactly the five unique distributions required")
    manifest = {"manifest_version":"option-flow-qualification1", "artifacts":sources}
    raw = canonical(manifest)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"candidate_manifest":str(args.output.resolve()),
        "candidate_manifest_sha256":sha256(b"option-flow-qualification1\n" + raw).hexdigest(),
        "artifacts":artifacts, "authorized":False,
        "next":"Independent coordinator artifact/source review must establish the out-of-band trust anchor before verify_flow_installed."}))

if __name__ == "__main__":
    main()
