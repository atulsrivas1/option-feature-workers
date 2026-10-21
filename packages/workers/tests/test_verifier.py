"""Synthetic wheel-structure unit tests; not an actual installed cohort proof."""
import base64
import csv
from hashlib import sha256
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from option_feature_workers import Artifact, CohortVerificationError
from option_feature_workers.verification import _wheel_entries


def wheel(path, *, marker=True, corrupt_record=False, extra_bytecode=False, standalone_module=False):
    entries = {"option_feature_workers/__init__.py": b"# synthetic structure only\n",
               "option_feature_workers-0.1.0a1.dist-info/METADATA":
                   b"Metadata-Version: 2.4\nName: option-feature-workers\nVersion: 0.1.0a1\n"}
    if marker:
        entries["option_feature_workers/_build_identity.json"] = (
            '{"source_commit":"' + "a" * 40 + '"}').encode()
    if extra_bytecode:
        entries["option_feature_workers/__pycache__/unqualified.cpython-312.pyc"] = b"synthetic-not-executed"
    if standalone_module:
        entries["standalone.py"] = b"# synthetic standalone source, never imported\n"
    record = "option_feature_workers-0.1.0a1.dist-info/RECORD"
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for name, content in entries.items():
        value = base64.urlsafe_b64encode(sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow((name, "sha256=" + ("wrong" if corrupt_record else value), len(content)))
    writer.writerow((record, "", ""))
    entries[record] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return Artifact("option-feature-workers", "0.1.0a1", "a" * 40,
                    sha256(path.read_bytes()).hexdigest(), "workers")


class WheelTests(unittest.TestCase):
    def test_structural_wheel_validates_bytes_and_controlled_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toy.whl"
            artifact = wheel(path)
            self.assertIn("option_feature_workers/_build_identity.json", _wheel_entries(path, artifact))

    def test_missing_source_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toy.whl"
            with self.assertRaises(CohortVerificationError):
                _wheel_entries(path, wheel(path, marker=False))

    def test_record_tampering_is_rejected_even_with_matching_archive_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toy.whl"
            with self.assertRaises(CohortVerificationError):
                _wheel_entries(path, wheel(path, corrupt_record=True))

    def test_executable_bytecode_is_not_exempted_from_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toy.whl"
            with self.assertRaises(CohortVerificationError):
                _wheel_entries(path, wheel(path, extra_bytecode=True))

    def test_standalone_pure_module_layout_is_explicitly_not_admitted(self):
        # Reject the layout itself: an adjacent standalone.pyc or timestamp-valid
        # __pycache__ entry cannot bypass the package-directory closure check.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toy.whl"
            with self.assertRaises(CohortVerificationError):
                _wheel_entries(path, wheel(path, standalone_module=True))


if __name__ == "__main__":
    unittest.main()
