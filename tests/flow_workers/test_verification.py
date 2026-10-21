"""Isolated verifier negatives; no invented qualified artifact cohort."""
from dataclasses import replace
import platform
import unittest
import importlib.machinery
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from option_flow_workers import FlowArtifact, FlowCohort, FlowCohortVerificationError
from option_flow_workers.verification import _validate, sysconfig_platform, require_verified_flow_cohort, _verify_module_origins

PROJECTS = (("option-flow-contracts", "contracts"), ("option-flow-features", "calculations"),
            ("option-flow-io", "io"), ("option-flow-workers", "workers"), ("duckdb", "dependency"))

def candidate():
    artifacts = tuple(sorted((FlowArtifact(name, "1.5.6" if name == "duckdb" else "0.1.0a1",
        "802a345bb627435d2a05d63cb74454fa98b60b5e" if name == "duckdb" else "a"*40,
        "b"*64, role) for name, role in PROJECTS), key=lambda item:item.distribution))
    return FlowCohort("option-flow-cohort1", platform.python_version(), sysconfig_platform(), artifacts)

class VerificationNegatives(unittest.TestCase):
    def test_unanchored_cohort_cannot_execute(self):
        with self.assertRaises(FlowCohortVerificationError):
            require_verified_flow_cohort(candidate())

    def test_r25_six_distribution_inventory_is_not_flow(self):
        c = candidate()
        c = replace(c, artifacts=tuple(sorted(c.artifacts + (FlowArtifact("python-flint", "0.9.0", "a"*40, "c"*64, "dependency"),), key=lambda item:item.distribution)))
        with self.assertRaises(FlowCohortVerificationError):
            _validate(c)

    def test_missing_artifact_not_admitted(self):
        with self.assertRaises(FlowCohortVerificationError):
            _validate(replace(candidate(), artifacts=candidate().artifacts[:-1]))

    def test_arbitrary_future_package_version_not_admitted(self):
        c = candidate()
        with self.assertRaises(FlowCohortVerificationError):
            _validate(replace(c, artifacts=tuple(replace(a, version="9.9") if a.role == "workers" else a for a in c.artifacts)))

    def test_native_upstream_source_not_inferred_from_version(self):
        c = candidate()
        with self.assertRaises(FlowCohortVerificationError):
            _validate(replace(c, artifacts=tuple(replace(a, source_commit="f"*40) if a.distribution == "duckdb" else a for a in c.artifacts)))

class DescendantOriginTampering(unittest.TestCase):
    def fixture(self, temporary):
        root = Path(temporary)
        package = root / "flow_verified_fixture"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "engine.py").write_text("VALUE = 1", encoding="utf-8")
        expected = {"flow_verified_fixture":((package / "__init__.py").resolve(), package.resolve()),
                    "flow_verified_fixture.engine":((package / "engine.py").resolve(), None)}
        loaded = ModuleType("flow_verified_fixture")
        loaded.__file__ = str(package / "__init__.py")
        loaded.__path__ = [str(package)]
        loaded.__spec__ = importlib.machinery.ModuleSpec("flow_verified_fixture", None,
            origin=str(package / "__init__.py"), is_package=True)
        loaded.__spec__.submodule_search_locations = [str(package)]
        return root, package, expected, loaded

    def test_loaded_descendant_shadow_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, package, expected, loaded = self.fixture(temporary)
            shadow = ModuleType("flow_verified_fixture.engine")
            shadow.__file__ = str(root / "foreign_engine.py")
            shadow.__spec__ = importlib.machinery.ModuleSpec(shadow.__name__, None, origin=shadow.__file__)
            with patch.dict(sys.modules, {"flow_verified_fixture":loaded, "flow_verified_fixture.engine":shadow}), patch.object(sys, "path", [str(root)] + sys.path):
                with self.assertRaises(FlowCohortVerificationError):
                    _verify_module_origins(expected)

    def test_altered_loaded_package_search_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, package, expected, loaded = self.fixture(temporary)
            foreign = root / "foreign"
            foreign.mkdir()
            loaded.__path__ = [str(foreign)]
            with patch.dict(sys.modules, {"flow_verified_fixture":loaded}), patch.object(sys, "path", [str(root)] + sys.path):
                with self.assertRaises(FlowCohortVerificationError):
                    _verify_module_origins(expected)

    def test_importable_descendant_shadow_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, package, expected, loaded = self.fixture(temporary)
            class ForeignFinder:
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "flow_verified_fixture.engine":
                        return importlib.machinery.ModuleSpec(fullname, None, origin=str(root / "foreign_engine.py"))
                    return None
            with patch.dict(sys.modules, {"flow_verified_fixture":loaded}), patch.object(sys, "path", [str(root)] + sys.path), patch.object(sys, "meta_path", [ForeignFinder()] + sys.meta_path):
                with self.assertRaises(FlowCohortVerificationError):
                    _verify_module_origins(expected)

    def test_exact_package_and_descendant_origins_are_accepted_without_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, package, expected, loaded = self.fixture(temporary)
            with patch.dict(sys.modules, {"flow_verified_fixture":loaded}), patch.object(sys, "path", [str(root)] + sys.path):
                origins = _verify_module_origins(expected)
                self.assertEqual(origins["flow_verified_fixture.engine"], str((package / "engine.py").resolve()))
                self.assertNotIn("flow_verified_fixture.engine", sys.modules)

if __name__ == "__main__":
    unittest.main()
