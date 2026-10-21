"""Isolated verifier negatives; no invented qualified artifact cohort."""
from dataclasses import replace
import platform
import unittest
import importlib.machinery
from contextlib import contextmanager
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from option_flow_workers import FlowArtifact, FlowCohort, FlowCohortVerificationError
from option_flow_workers.verification import _validate, sysconfig_platform, require_verified_flow_cohort, _verify_module_origins, _native_descendant_origins, _NATIVE_CHILD_EXPORTS

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

class ClosedNativeChildProfile(unittest.TestCase):
    @contextmanager
    def profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            native = Path(temporary) / ("_duckdb" + importlib.machinery.EXTENSION_SUFFIXES[0])
            native.write_bytes(b"synthetic-profile-shape-only-not-a-native-artifact")
            parent = ModuleType("_duckdb")
            parent.__file__ = str(native)
            parent.__spec__ = importlib.machinery.ModuleSpec("_duckdb", None, origin=str(native))
            children = {}
            for name, exports in _NATIVE_CHILD_EXPORTS.items():
                child = ModuleType(name)
                child.__file__ = str(native)
                for export in exports:
                    setattr(child, export, object())
                children[name] = child
                setattr(parent, name.rpartition(".")[2], child)
            modules = {"_duckdb":(native.resolve(), None)}
            verified = {"_duckdb":str(native.resolve())}
            with patch.dict(sys.modules, {"_duckdb":parent, **children}):
                yield parent, children, modules, verified

    def test_literal_profile_accepts_exact_two_children_bound_to_verified_parent(self):
        self.assertEqual(set(_NATIVE_CHILD_EXPORTS), {"_duckdb._func", "_duckdb._sqltypes"})
        self.assertEqual(_NATIVE_CHILD_EXPORTS["_duckdb._func"],
                         ("ARROW", "DEFAULT", "FunctionNullHandling", "NATIVE", "PythonUDFType", "SPECIAL"))
        with self.profile() as (parent, children, modules, verified):
            origins = _native_descendant_origins(modules, verified)
            self.assertEqual(set(origins), {"_duckdb._func", "_duckdb._sqltypes"})
            self.assertTrue(all(value == str(Path(parent.__file__).resolve()) for value in origins.values()))

    def test_altered_native_child_file_is_rejected(self):
        with self.profile() as (parent, children, modules, verified):
            children["_duckdb._func"].__file__ += ".foreign"
            with self.assertRaises(FlowCohortVerificationError):
                _native_descendant_origins(modules, verified)

    def test_native_child_spec_loader_package_or_path_is_rejected(self):
        for field, value in (("__spec__", object()), ("__loader__", object()),
                             ("__package__", "foreign"), ("__path__", [])):
            with self.subTest(field=field), self.profile() as (parent, children, modules, verified):
                setattr(children["_duckdb._func"], field, value)
                with self.assertRaises(FlowCohortVerificationError):
                    _native_descendant_origins(modules, verified)

    def test_native_child_parent_attribute_identity_is_required(self):
        for mutation in ("replacement", "deletion"):
            with self.subTest(mutation=mutation), self.profile() as (parent, children, modules, verified):
                if mutation == "replacement":
                    parent._func = ModuleType("_duckdb._func")
                else:
                    del parent._func
                with self.assertRaises(FlowCohortVerificationError):
                    _native_descendant_origins(modules, verified)

    def test_native_child_name_and_exact_module_type_are_required(self):
        with self.profile() as (parent, children, modules, verified):
            children["_duckdb._func"].__name__ = "_duckdb.impostor"
            with self.assertRaises(FlowCohortVerificationError):
                _native_descendant_origins(modules, verified)
        with self.profile() as (parent, children, modules, verified):
            class Submodule(ModuleType):
                pass
            replacement = Submodule("_duckdb._func")
            replacement.__dict__.update(vars(children["_duckdb._func"]))
            parent._func = replacement
            with patch.dict(sys.modules, {"_duckdb._func":replacement}):
                with self.assertRaises(FlowCohortVerificationError):
                    _native_descendant_origins(modules, verified)

    def test_native_children_require_complete_closed_export_inventory(self):
        for mutation in ("missing_child", "extra_export", "missing_export"):
            with self.subTest(mutation=mutation), self.profile() as (parent, children, modules, verified):
                if mutation == "missing_child":
                    sys.modules.pop("_duckdb._sqltypes")
                elif mutation == "extra_export":
                    children["_duckdb._func"].UNREVIEWED_EXPORT = object()
                else:
                    del children["_duckdb._func"].ARROW
                with self.assertRaises(FlowCohortVerificationError):
                    _native_descendant_origins(modules, verified)

    def test_third_native_descendant_remains_rejected(self):
        with self.profile() as (parent, children, modules, verified):
            extra = ModuleType("_duckdb.unreviewed")
            extra.__file__ = parent.__file__
            parent.unreviewed = extra
            with patch.dict(sys.modules, {"_duckdb.unreviewed":extra}), patch.object(sys, "path", [str(Path(parent.__file__).parent)] + sys.path):
                with self.assertRaises(FlowCohortVerificationError):
                    _verify_module_origins(modules)

    def test_unverified_native_parent_cannot_authorize_children(self):
        with self.profile() as (parent, children, modules, verified):
            self.assertEqual(_native_descendant_origins(modules, {}), {})
            self.assertEqual(_native_descendant_origins({}, verified), {})
        with self.subTest(mutation="root_meta_path_shadow"), self.profile() as (parent, children, modules, verified):
            class ForeignNativeFinder:
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "_duckdb":
                        return importlib.machinery.ModuleSpec(fullname, None, origin=parent.__file__ + ".foreign")
                    return None
            with patch.object(sys, "meta_path", [ForeignNativeFinder()] + sys.meta_path):
                with self.assertRaises(FlowCohortVerificationError):
                    _verify_module_origins(modules)

if __name__ == "__main__":
    unittest.main()
