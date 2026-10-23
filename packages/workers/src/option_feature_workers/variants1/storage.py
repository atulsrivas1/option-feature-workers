"""DuckDB sink for option-flow-variants1 generations.

One owned connection, one thread, a new variant-only destination. A publication
is inserted atomically with its objects, operation receipts, bindings and optional
checkpoint; a retry of the same run key first verifies the stored generation and
is either identical (already_committed) or a PublicationConflict. Earlier
generations are never overwritten or deleted.
"""
import json

import duckdb

from option_feature_contracts.variants1.canonical import (
    SCHEMA_GENERATION, SCHEMA_JSON, canonical_json, cohort_digest, content_digest, record_digest,
)

from .errors import VariantWorkerError


class PublicationConflict(VariantWorkerError):
    """The run key already holds a different complete publication."""

    def __init__(self, message="publication_conflict"):
        super().__init__("publication_conflict")
        self.detail = message


class StorageIntegrityError(VariantWorkerError):
    """Stored rows do not match the canonical publication they claim."""

    def __init__(self, message="storage_integrity"):
        super().__init__("storage_integrity")
        self.detail = message


class StorageSchemaError(VariantWorkerError):
    """The destination schema is not exactly the proposed variant schema."""

    def __init__(self, message="storage_schema"):
        super().__init__("storage_schema")
        self.detail = message


_VARCHAR, _BIGINT = "VARCHAR", "BIGINT"
_CHILD = ("variant_objects", "variant_operations", "variant_bindings")
# (table, ((column, type, nullable), ...), primary key columns)
_TABLES = (
    ("variant_schema", (("version", _VARCHAR, False),), ("version",)),
    ("variant_generations", (
        ("run_key", _VARCHAR, False), ("work_sha256", _VARCHAR, False), ("request_sha256", _VARCHAR, False),
        ("snapshot_sha256", _VARCHAR, False), ("cohort_sha256", _VARCHAR, False),
        ("input_checkpoint_sha256", _VARCHAR, True), ("results_sha256", _VARCHAR, False),
        ("output_checkpoint_sha256", _VARCHAR, True), ("publication_sha256", _VARCHAR, False),
        ("object_count", _BIGINT, False), ("operation_count", _BIGINT, False),
        ("canonical_publication", _VARCHAR, False), ("state", _VARCHAR, False)), ("run_key",)),
    ("variant_objects", (("run_key", _VARCHAR, False), ("ordinal", _BIGINT, False),
                         ("record_sha256", _VARCHAR, False), ("canonical_record", _VARCHAR, False)),
     ("run_key", "ordinal")),
    ("variant_operations", (("run_key", _VARCHAR, False), ("ordinal", _BIGINT, False),
                            ("record_sha256", _VARCHAR, False), ("canonical_record", _VARCHAR, False)),
     ("run_key", "ordinal")),
    ("variant_bindings", (("run_key", _VARCHAR, False), ("ordinal", _BIGINT, False),
                          ("record_sha256", _VARCHAR, False), ("canonical_record", _VARCHAR, False)),
     ("run_key", "ordinal")),
    ("variant_checkpoints", (("run_key", _VARCHAR, False), ("record_sha256", _VARCHAR, False),
                             ("canonical_record", _VARCHAR, False)), ("run_key",)),
)
_TABLE_NAMES = tuple(t[0] for t in _TABLES)
_ORDER = {t[0]: t[2] for t in _TABLES}


def _ddl():
    out = []
    for name, cols, pk in _TABLES:
        parts = ["%s %s%s" % (c, t, "" if nullable else " NOT NULL") for c, t, nullable in cols]
        parts.append("PRIMARY KEY (%s)" % ", ".join(pk))
        out.append("CREATE TABLE %s (%s)" % (name, ", ".join(parts)))
    return out


def envelope(record_type, record):
    """Canonical envelope text of one typed record."""
    return canonical_json({
        "content_sha256": content_digest(record_type, record), "payload": record,
        "record_type": record_type, "schema_version": SCHEMA_JSON,
    }).decode("utf-8")


def _unwrap(text, record_type):
    """Decode an envelope and verify its type, digest and canonical form."""
    try:
        doc = json.loads(text)
    except (TypeError, ValueError):
        raise StorageIntegrityError("undecodable record") from None
    if (not isinstance(doc, dict) or doc.get("record_type") != record_type
            or doc.get("schema_version") != SCHEMA_JSON or "payload" not in doc):
        raise StorageIntegrityError("record envelope")
    if envelope(record_type, doc["payload"]) != text:
        raise StorageIntegrityError("record bytes")
    return doc["payload"]


def _generation_row(pub, canonical_publication):
    cp = pub["output_checkpoint"]
    return (
        pub["run_key"], pub["work_sha256"], pub["request_sha256"], pub["snapshot_sha256"], pub["cohort_sha256"],
        pub["input_checkpoint_sha256"], record_digest("variant_Results", pub["results"]),
        None if cp is None else record_digest("variant_Checkpoint", cp),
        record_digest("variant_Publication", pub), len(pub["results"]["rows"]),
        len(pub["results"]["operations"]), canonical_publication, "committed",
    )


def _children(pub):
    """(table, record_type, [records]) in storage order."""
    return (("variant_objects", "variant_Result", pub["results"]["rows"]),
            ("variant_operations", "variant_OperationReceipt", pub["results"]["operations"]),
            ("variant_bindings", "variant_Binding", pub["bindings"]))


def commit_receipt(pub, outcome):
    cp = pub["output_checkpoint"]
    return {
        "run_key": pub["run_key"], "work_sha256": pub["work_sha256"],
        "publication_sha256": record_digest("variant_Publication", pub),
        "results_sha256": record_digest("variant_Results", pub["results"]),
        "output_checkpoint_sha256": None if cp is None else record_digest("variant_Checkpoint", cp),
        "object_count": len(pub["results"]["rows"]), "outcome": outcome, "verified_readback": True,
    }


class VariantDuckDBSink:
    """Variant-only DuckDB destination: publish, read, close, context manager."""

    def __init__(self, destination):
        self._con = duckdb.connect(str(destination))
        self._con.execute("SET threads TO 1")
        try:
            self._open()
        except BaseException:
            self._con.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        if self._con is not None:
            self._con.close()
            self._con = None

    # ---- schema ---------------------------------------------------------
    def _open(self):
        names = [r[0] for r in self._con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE NOT internal").fetchall()]
        if not names and not self._other_objects():
            self._con.execute("BEGIN")
            try:
                for stmt in _ddl():
                    self._con.execute(stmt)
                self._con.execute("INSERT INTO variant_schema VALUES (?)", [SCHEMA_GENERATION])
                self._con.execute("COMMIT")
            except BaseException:
                self._con.execute("ROLLBACK")
                raise
            return
        self._check_schema()

    def _other_objects(self):
        con = self._con
        out = []
        out += [["view", r[0]] for r in con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()]
        out += [["sequence", r[0]] for r in con.execute("SELECT sequence_name FROM duckdb_sequences()").fetchall()]
        out += [["type", r[0]] for r in con.execute(
            "SELECT type_name FROM duckdb_types() WHERE NOT internal").fetchall()]
        out += [["macro", r[0]] for r in con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE NOT internal").fetchall()]
        out += [["schema", r[0]] for r in con.execute(
            "SELECT schema_name FROM duckdb_schemas() WHERE NOT internal AND schema_name <> 'main'").fetchall()]
        return out

    def _schema_tableau(self):
        con = self._con
        tables = [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables() WHERE NOT internal").fetchall()]
        schema = []
        for name in _TABLE_NAMES:
            if name not in tables:
                continue
            cols = con.execute(
                "SELECT column_name, data_type, is_nullable FROM duckdb_columns() "
                "WHERE table_name = ? ORDER BY column_index", [name]).fetchall()
            pk = []
            for ctype, names in con.execute(
                    "SELECT constraint_type, constraint_column_names FROM duckdb_constraints() "
                    "WHERE table_name = ?", [name]).fetchall():
                if ctype == "PRIMARY KEY":
                    pk = list(names)
            schema.append([name, [[c, t, bool(n), pk.index(c) + 1 if c in pk else 0] for c, t, n in cols]])
        return {
            "schema": schema,
            "extra_tables": sorted(t for t in tables if t not in _TABLE_NAMES),
            "defaults": [r[0] for r in con.execute(
                "SELECT table_name || '.' || column_name FROM duckdb_columns() "
                "WHERE column_default IS NOT NULL AND NOT internal").fetchall()],
            "extensions": sorted(r[0] for r in con.execute(
                "SELECT extension_name FROM duckdb_extensions() WHERE loaded AND install_mode <> 'STATICALLY_LINKED'"
            ).fetchall()),
            "foreign_keys": [r[0] for r in con.execute(
                "SELECT table_name FROM duckdb_constraints() WHERE constraint_type = 'FOREIGN KEY'").fetchall()],
            "other_objects": self._other_objects(),
            "triggers": [],
            "user_indexes": [r[0] for r in con.execute("SELECT index_name FROM duckdb_indexes()").fetchall()],
        }

    def _check_schema(self):
        t = self._schema_tableau()
        expected = []
        for name, cols, pk in _TABLES:
            expected.append([name, [[c, ty, nl, pk.index(c) + 1 if c in pk else 0] for c, ty, nl in cols]])
        if (t["schema"] != expected or t["extra_tables"] or t["defaults"] or t["extensions"]
                or t["foreign_keys"] or t["other_objects"] or t["user_indexes"]):
            raise StorageSchemaError("schema")
        rows = self._con.execute("SELECT version FROM variant_schema").fetchall()
        if rows != [(SCHEMA_GENERATION,)]:
            raise StorageSchemaError("schema row")

    def tableau(self):
        """Complete stored tableau: schema facts and every row in primary-key order."""
        t = self._schema_tableau()
        out = {k: t[k] for k in ("defaults", "extensions", "foreign_keys", "other_objects", "schema",
                                 "triggers", "user_indexes")}
        tables = {}
        for name in sorted(_TABLE_NAMES):
            order = ", ".join(_ORDER[name])
            tables[name] = [list(r) for r in self._con.execute(
                "SELECT * FROM %s ORDER BY %s" % (name, order)).fetchall()]
        out["tables"] = tables
        return out

    # ---- reading --------------------------------------------------------
    def _rows(self, table, run_key):
        order = ", ".join(_ORDER[table])
        return self._con.execute("SELECT * FROM %s WHERE run_key = ? ORDER BY %s" % (table, order),
                                 [run_key]).fetchall()

    def read(self, run_key):
        """Decode and verify one stored generation; None when the run key is absent."""
        self._check_schema()
        gens = self._con.execute("SELECT * FROM variant_generations WHERE run_key = ?", [run_key]).fetchall()
        if not gens:
            for table in _CHILD + ("variant_checkpoints",):
                if self._rows(table, run_key):
                    raise StorageIntegrityError("orphan rows")
            return None
        return self._verify_generation(gens[0])

    def _verify_generation(self, gen):
        (run_key, work, request_h, snapshot_h, cohort_h, input_cp, results_h, output_cp, pub_h,
         object_count, operation_count, canonical, state) = gen
        if state != "committed" or object_count < 0 or operation_count < 0:
            raise StorageIntegrityError("generation metadata")
        pub = _unwrap(canonical, "variant_Publication")
        if pub.get("schema_version") != SCHEMA_GENERATION or pub.get("run_key") != run_key:
            raise StorageIntegrityError("publication identity")
        if _generation_row(pub, canonical) != tuple(gen):
            raise StorageIntegrityError("generation row")
        for table, rtype, records in _children(pub):
            rows = self._rows(table, run_key)
            if len(rows) != len(records):
                raise StorageIntegrityError("%s count" % table)
            for i, (row, rec) in enumerate(zip(rows, records)):
                if tuple(row) != (run_key, i, record_digest(rtype, rec), envelope(rtype, rec)):
                    raise StorageIntegrityError("%s row %d" % (table, i))
        cps = self._rows("variant_checkpoints", run_key)
        cp = pub["output_checkpoint"]
        if cp is None:
            if cps:
                raise StorageIntegrityError("checkpoint row")
        elif [tuple(r) for r in cps] != [(run_key, record_digest("variant_Checkpoint", cp),
                                          envelope("variant_Checkpoint", cp))]:
            raise StorageIntegrityError("checkpoint row")
        return pub

    def verify(self):
        """Verify the whole destination: every generation and no orphan rows."""
        self._check_schema()
        keys = set()
        for gen in self._con.execute("SELECT * FROM variant_generations ORDER BY run_key").fetchall():
            self._verify_generation(gen)
            keys.add(gen[0])
        for table in _CHILD + ("variant_checkpoints",):
            for (run_key,) in self._con.execute("SELECT DISTINCT run_key FROM %s" % table).fetchall():
                if run_key not in keys:
                    raise StorageIntegrityError("orphan rows")

    # ---- writing --------------------------------------------------------
    def publish(self, publication):
        """Atomically store one canonical publication; returns a CommitReceipt record."""
        self.verify()
        stored = self.read(publication["run_key"])
        if stored is not None:
            if canonical_json(stored) == canonical_json(publication):
                return commit_receipt(publication, "already_committed")
            raise PublicationConflict("different publication under the run key")
        if (publication.get("schema_version") != SCHEMA_GENERATION
                or cohort_digest(publication["cohort"]) != publication["cohort_sha256"]):
            raise VariantWorkerError("execution_failed")
        canonical = envelope("variant_Publication", publication)
        run_key = publication["run_key"]
        con = self._con
        con.execute("BEGIN")
        try:
            con.execute("INSERT INTO variant_generations VALUES (%s)" % ", ".join("?" * 13),
                        list(_generation_row(publication, canonical)))
            for table, rtype, records in _children(publication):
                for i, rec in enumerate(records):
                    con.execute("INSERT INTO %s VALUES (?, ?, ?, ?)" % table,
                                [run_key, i, record_digest(rtype, rec), envelope(rtype, rec)])
            cp = publication["output_checkpoint"]
            if cp is not None:
                con.execute("INSERT INTO variant_checkpoints VALUES (?, ?, ?)",
                            [run_key, record_digest("variant_Checkpoint", cp), envelope("variant_Checkpoint", cp)])
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        again = self.read(run_key)
        if again is None or canonical_json(again) != canonical_json(publication):
            raise StorageIntegrityError("readback differs")
        return commit_receipt(publication, "committed")
