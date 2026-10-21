"""Archive admission regressions for the private build helper; not build proof."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("flow_build_helper_tested", Path(__file__).resolve().parents[2] / "tools" / "flow_build_artifacts.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)

class SafeArchiveAdmission(unittest.TestCase):
    def archive(self, root, entries):
        path = root / "source.tar"
        with tarfile.open(path, "w") as stream:
            for name, kind, contents in entries:
                info = tarfile.TarInfo(name)
                if kind == "link":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "../outside"
                    stream.addfile(info)
                else:
                    payload = contents.encode("utf-8")
                    info.size = len(payload)
                    stream.addfile(info, io.BytesIO(payload))
        return path

    def test_normal_archive_preserves_literal_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [("packages/flow-contracts/src/module.py", "file", "VALUE = 23\n")])
            destination = root / "staged"
            HELPER.safe_extract(archive, destination)
            self.assertEqual((destination / "packages/flow-contracts/src/module.py").read_bytes(), b"VALUE = 23\n")

    def test_traversal_absolute_windows_device_and_link_members_are_rejected_before_source_writes(self):
        for name, kind in (("../escape", "file"), ("/escape", "file"), ("C:/escape", "file"),
                           ("packages/NUL", "file"), ("packages/link", "link")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self.archive(root, [("safe", "file", "must-not-be-written"), (name, kind, "unsafe")])
                destination = root / "staged"
                with self.assertRaises(ValueError):
                    HELPER.safe_extract(archive, destination)
                self.assertFalse((destination / "safe").exists())
                self.assertFalse((root / "escape").exists())

    def test_duplicate_normalized_members_are_rejected_before_source_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [("package/entry", "file", "first"), ("package/./entry", "file", "second")])
            destination = root / "staged"
            with self.assertRaises(ValueError):
                HELPER.safe_extract(archive, destination)
            self.assertFalse((destination / "package/entry").exists())

    def test_existing_staging_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [("file", "file", "value")])
            destination = root / "staged"
            destination.mkdir()
            with self.assertRaises(FileExistsError):
                HELPER.safe_extract(archive, destination)

if __name__ == "__main__":
    unittest.main()
