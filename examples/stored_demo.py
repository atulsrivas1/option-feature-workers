"""Run only after protected runtime hold is released and artifacts qualify.

No server or browser launch is hidden here. Output is a local HTML file derived
from actual stored readback, with full direct/worker/stored canonical parity.
"""
import argparse
import hashlib
from html import escape
import json
import os
import sys
import tempfile
from pathlib import Path

# R27 T6: python -I does not put the script directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from option_feature_contracts import canonical_bytes
from option_feature_io import DuckDBSink
from option_feature_workers import (
    Artifact, Cohort, ExecutionConfig, QualificationManifest, QualificationSource,
    execute, verify_installed_cohort,
)
from option_features import evaluate
from synthetic_scenario import assert_scenario_results, scenario


class NeverCancel:
    def is_cancelled(self) -> bool:
        return False


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a same-directory temp file and os.replace; never leave a partial file."""
    path = Path(path)
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _exact(mapping, names):
    if type(mapping) is not dict or set(mapping) != set(names):
        raise ValueError("Unknown or missing qualification configuration fields")
    return mapping


def load_configuration(path: Path, trusted_manifest_sha256: str, destination: Path) -> Cohort:
    config = _exact(json.loads(path.read_text(encoding="utf-8")),
                    ("cohort", "qualification_manifest", "wheel_paths"))
    raw = _exact(config["cohort"], ("cohort_version", "python_version", "platform_id", "artifacts"))
    artifacts = tuple(Artifact(**_exact(row, ("distribution", "version", "source_commit", "wheel_sha256", "role")))
                      for row in raw["artifacts"])
    cohort = Cohort(raw["cohort_version"], raw["python_version"], raw["platform_id"], artifacts)
    raw_manifest = _exact(config["qualification_manifest"], ("manifest_version", "artifacts"))
    sources = tuple(QualificationSource(**_exact(row, (
        "distribution", "version", "source_commit", "wheel_sha256", "source_reference",
        "build_receipt_path", "build_receipt_sha256"))) for row in raw_manifest["artifacts"])
    manifest = QualificationManifest(raw_manifest["manifest_version"], sources)
    destination.mkdir(parents=True, exist_ok=True)
    verify_installed_cohort(cohort, tuple(config["wheel_paths"]),
                            str(destination / "installed-verification.json"), manifest,
                            trusted_manifest_sha256)
    return cohort


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--trusted-manifest-sha256", required=True,
                        help="Independently reviewed coordinator digest; never take it from input data")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--run-prefix", default="r25-demo1-",
                        help="run_key prefix (default keeps the R25 keys)")
    args = parser.parse_args()
    destination = args.destination.resolve()
    cohort = load_configuration(args.config, args.trusted_manifest_sha256, destination)
    execution = ExecutionConfig("batch", 1, 1, 67108864, 16777216, 1, 1)
    sink = DuckDBSink(str(destination / "synthetic-output.duckdb"))
    tables = []
    evidence = []
    for variant in ("complete", "unsupported", "missing_spot", "future_spot", "partial_quotes"):
        snapshot, request = scenario(variant)
        direct = evaluate(snapshot, request)
        assert_scenario_results(variant, direct)
        receipt = execute(snapshot, request, execution, cohort,
                          args.run_prefix + variant, sink, NeverCancel())
        stored = sink.read(receipt.run_key)
        if stored is None or not (canonical_bytes(direct) == canonical_bytes(receipt.results)
                                  == canonical_bytes(stored.results)):
            raise RuntimeError("Full canonical direct/worker/stored parity failed")
        assert_scenario_results(variant, receipt.results)
        assert_scenario_results(variant, stored.results)
        rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in
                       (row.contract_id, row.output_id, row.value, row.status, row.reason,
                        row.quality_flags, row.coverage)) + "</tr>" for row in stored.results)
        tables.append(f"<h2>{escape(variant)}</h2><table><thead><tr>"
                      "<th>Contract</th><th>Output</th><th>Value</th><th>Status</th><th>Reason</th>"
                      f"<th>Quality</th><th>Coverage</th></tr></thead><tbody>{rows}</tbody></table>")
        bindings = [{"binding_id": b.binding_id, "source_id": b.source_id,
                     "source_content_sha256": b.source_content_sha256} for b in stored.bindings]
        if not bindings or any(len(b["source_content_sha256"]) != 64 for b in bindings):
            raise RuntimeError("Stored source bindings missing or malformed")
        prov = ("<table class='prov'><tbody>"
                f"<tr><th>run_key</th><td>{escape(receipt.run_key)}</td></tr>"
                f"<tr><th>work_sha256</th><td>{escape(receipt.work_sha256)}</td></tr>"
                f"<tr><th>cohort_sha256</th><td>{escape(stored.cohort_sha256)}</td></tr>"
                + "".join(f"<tr><th>source {escape(b['source_id'])} (binding {escape(b['binding_id'])})"
                          f" source_content_sha256</th><td>{escape(b['source_content_sha256'])}</td></tr>"
                          for b in bindings) + "</tbody></table>")
        tables[-1] = tables[-1].replace("</h2>", "</h2>" + prov, 1)
        evidence.append({"scenario": variant, "run_key": receipt.run_key,
                         "work_sha256": receipt.work_sha256, "outcome": receipt.outcome,
                         "cohort_sha256": stored.cohort_sha256, "bindings": bindings,
                         "full_canonical_parity": True, "scenario_semantics_verified": True})
    sink.close()
    evidence_text = json.dumps(evidence, indent=2) + "\n"
    evidence_sha = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
    html = ("<!doctype html><html lang='en'><meta charset='utf-8'><title>R25 synthetic stored output</title>"
            "<style>body{font-family:system-ui;padding:24px}table{border-collapse:collapse;width:100%}"
            "code{word-break:break-all}td{word-break:break-all}td,th{border:1px solid #ccc;padding:7px;text-align:left}th{background:#eef}</style>"
            "<h1>R25 synthetic stored output</h1><p>Actual persisted readback. Original synthetic inputs; "
            "no private/provider feed. All fields, statuses, quality, coverage and solver/provenance identities "
            "were compared as complete canonical result payloads. This is integration evidence, "
            "not an independent numerical oracle or a release certificate.</p>"
            f"<p>Provenance: cohort_version {escape(cohort.cohort_version)}; demo-evidence.json sha256 "
            f"<code>{evidence_sha}</code>. Hashes below are full and equal demo-evidence.json and the "
            "DuckDB generations/source_bindings rows.</p>" + "".join(tables) + "</html>")
    # Evidence first: the page names its sha256, so a page/evidence mismatch is detectable.
    atomic_write_text(destination / "demo-evidence.json", evidence_text)
    atomic_write_text(destination / "index.html", html)
    print(destination / "index.html")


if __name__ == "__main__":
    main()
