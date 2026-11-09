"""Capture one full typed R1 input entity; plan two loads without executing DML."""

import ast
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from scripts.r1_business_snapshot_contract import frame, load_schema
from scripts.r1_integration_evidence import (
    deny_real,
    label,
    sha,
    source_identity,
    verify_business_sources,
)
from scripts.r1_real_root_protocol import require
from scripts.r1_seed_snapshot_recipe import (
    FROZEN_COLUMNS,
    expected_counts,
    recipe_template,
    snapshot_input_rows,
)

FROZEN_TIME = datetime(2025, 1, 1, microsecond=1, tzinfo=UTC)


def input_catalog(schema):
    """Source index/constraint/enum identities, not observations of a live PG."""
    root = Path(__file__).resolve().parents[1]
    trees = {}
    result = {}
    for table in expected_counts():
        spec = schema["tables"][table]
        path = next(iter(spec["columns"].values()))["source"]["path"]
        if path not in trees:
            trees[path] = ast.parse((root / path).read_text("utf8"))
        cls = next(
            n
            for n in trees[path].body
            if isinstance(n, ast.ClassDef) and n.name == spec["source_class"]
        )
        indexes, constraints = [], []
        for node in ast.walk(cls):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in (
                    "Index",
                    "UniqueConstraint",
                ):
                    indexes.append(ast.unparse(node))
                if isinstance(node.func, ast.Name) and node.func.id == "CheckConstraint":
                    constraints.append(ast.unparse(node))
                if isinstance(node.func, ast.Name) and node.func.id == "mapped_column":
                    for kw in node.keywords:
                        if (
                            kw.arg in ("index", "unique")
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            indexes.append(ast.unparse(node))
        result[table] = {
            "columns": spec["columns"],
            "primary_key": spec["primary_key"],
            "natural_key": spec["natural_key"],
            "indexes": sorted(indexes),
            "check_constraints": sorted(constraints),
            "pg_enums": [],
            "basis": "PINNED_ORM_SOURCE_NOT_LIVE_PG",
        }
    return result


def entity_digest(entity):
    schema = load_schema()
    canonical = dict(entity)
    canonical["tables"] = {}
    for table, rows in entity["tables"].items():
        spec = schema["tables"][table]
        keys = list(dict.fromkeys(spec["natural_key"] + spec["primary_key"]))
        canonical["tables"][table] = sorted(
            rows, key=lambda r, keys=keys: frame(tuple(r[k] for k in keys))
        )
    return sha(canonical)


def original_fixture_oracle():
    """Independently interpret pinned seed keyword AST and mapped-column defaults.

    Only this fixture's finite expression vocabulary is supported: no exec/eval,
    ORM import, Settings, connection or Seed invocation. Unknown syntax refuses.
    The fixed 420-day/weekday call layout is separately pinned by source hashes.
    Every populated field carries its origin; only five listed times are frozen.
    """
    verify_business_sources()
    root, schema = Path(__file__).resolve().parents[1], load_schema()
    fixture = "tests/integration/test_business_recalc_performance.py"
    tree = ast.parse((root / fixture).read_text("utf8"))
    seed = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "seed")
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(420)]

    def expression(node, env):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.Subscript):
            return expression(node.value, env)[expression(node.slice, env)]
        if isinstance(node, ast.Attribute) and node.attr == "weekday":
            return expression(node.value, env).weekday
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "d.weekday":
            return env["d"].weekday()
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Lt):
            return expression(node.left, env) < expression(node.comparators[0], env)
        require(False, "SEED_ORACLE_EXPRESSION_UNKNOWN")

    templates = {}
    stock_rows = calendar = None
    for node in ast.walk(seed):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "m":
                require(node.func.attr not in templates, "SEED_ORACLE_TEMPLATE_DUPLICATE")
                templates[node.func.attr] = node
            if ast.unparse(node.func) == "db.execute":
                if ast.unparse(node.args[0]) == "insert(m.StockBasic)":
                    stock_rows = node.args[1]
                elif ast.unparse(node.args[0]) == "insert(m.TradeCalendar)":
                    calendar = node.args[1].elt
    require(isinstance(stock_rows, ast.List) and len(stock_rows.elts) == 2
            and isinstance(calendar, ast.Call), "SEED_ORACLE_LAYOUT_UNKNOWN")
    tables, origins, sequences = {}, {}, {}
    for table in expected_counts():
        spec = schema["tables"][table]
        model_path = next(iter(spec["columns"].values()))["source"]["path"]
        cls = next(n for n in ast.parse((root / model_path).read_text("utf8")).body
                   if isinstance(n, ast.ClassDef) and n.name == spec["source_class"])
        declarations = {n.target.id: n.value for n in cls.body if isinstance(n, ast.AnnAssign)}
        rows, row_origins = [], []
        if table == "stock_basic":
            calls = [(n, {"days": days}) for n in stock_rows.elts]
        elif table == "trade_calendar":
            calls = [(calendar, {"d": day}) for day in days]
        elif spec["source_class"] not in templates:
            calls = []
        else:
            node = templates[spec["source_class"]]
            if table in ("sector", "sector_member"):
                calls = [(node, {"days": days})]
            else:
                codes = (("000300.SH", "000001.SH") if table == "index_daily" else
                         ("stock_st", "suspend_d") if table == "data_quality_daily" else
                         ("000001.SZ", "000002.SZ"))
                calls = [(node, {"day": day, "code": code, "dataset": code})
                         for day in days if day.weekday() < 5 for code in codes]
        serial_count = 0
        for call, env in calls:
            explicit = {kw.arg: expression(kw.value, env) for kw in call.keywords}
            require(set(explicit) <= set(spec["columns"]), "SEED_ORACLE_FIELD_UNKNOWN")
            row, provenance = {}, {}
            for column, rule in spec["columns"].items():
                decl = declarations[column]
                options = {kw.arg: kw.value for kw in decl.keywords}
                if column in explicit:
                    value, origin = explicit[column], "explicit_seed"
                elif "default" in options:
                    value, origin = ast.literal_eval(options["default"]), "orm_default"
                elif "server_default" in options:
                    require(table + "." + column in FROZEN_COLUMNS
                            and ast.unparse(options["server_default"]) == "func.now()",
                            "SEED_ORACLE_SERVER_DEFAULT_UNKNOWN")
                    value, origin = FROZEN_TIME, "frozen_timestamp"
                elif "autoincrement" in options and ast.literal_eval(options["autoincrement"]):
                    serial_count += 1
                    value, origin = serial_count, "serial_state"
                else:
                    require(rule["nullable"], "SEED_ORACLE_REQUIRED_FIELD_ABSENT")
                    value, origin = None, "nullable_absent"
                if value is not None and rule["type"] == "float":
                    value = float(value)
                row[column], provenance[column] = value, origin
            rows.append(row)
            row_origins.append(provenance)
        for column, decl in declarations.items():
            if isinstance(decl, ast.Call) and any(
                kw.arg == "autoincrement" and ast.literal_eval(kw.value) for kw in decl.keywords
            ):
                sequences[table + "." + column] = {
                    "last_value": serial_count or 1, "is_called": serial_count > 0, "increment": 1}
        tables[table], origins[table] = rows, row_origins
    require({t: len(r) for t, r in tables.items()} == expected_counts(), "SEED_ORACLE_ROWS")
    return {"tables": tables, "sequences": sequences,
            "fixture_sha": schema["sources"][fixture]["sha256"],
            "catalog": input_catalog(schema)}, origins


def generate_original_input():
    """Standalone deterministic generator matching original seed's supplied fields.

    Nullable defaults and server-generated serial/time defaults are made explicit.
    No ORM imports, Session, random calls, or mutation of the historical seed.
    Catalog identity here is a source contract, not a live PG catalog observation.
    """
    schema, start = load_schema(), date(2025, 1, 1)
    tables = {name: [] for name in expected_counts()}

    def add(table, **values):
        defaults = {}
        for column, rule in schema["tables"][table]["columns"].items():
            defaults[column] = (
                None
                if rule["nullable"]
                else {
                    "text": "",
                    "int": 1,
                    "float": 1.0,
                    "bool": False,
                    "date": start,
                    "datetime": FROZEN_TIME,
                    "json": {},
                }[rule["type"]]
            )
        defaults.update(values)
        tables[table].append(defaults)

    for code, closed in (("000001.SZ", False), ("000002.SZ", True)):
        add(
            "stock_basic",
            ts_code=code,
            list_date=start + timedelta(days=10) if closed else start,
            delist_date=start + timedelta(days=25) if closed else None,
            exchange="SZSE",
            list_status="D" if closed else "L",
        )
    add("sector", sector_id=101, source="SW", source_code="BIZ", name="synthetic", level="L1",
        is_active=True)
    add("sector_member", id=1, sector_id=101, ts_code="000001.SZ", valid_from=start, is_latest=True)
    quality = 0
    for i in range(420):
        day = start + timedelta(days=i)
        add("trade_calendar", cal_date=day, is_open=day.weekday() < 5, exchange="SSE")
        if day.weekday() >= 5:
            continue
        for code in ("000001.SZ", "000002.SZ"):
            add(
                "stock_daily",
                trade_date=day,
                ts_code=code,
                open=20.0,
                close=20.0,
                high=21.0,
                low=19.0,
                vol=100000.0,
                amount=1000000.0,
            )
            add("stock_adj_factor", trade_date=day, ts_code=code, adj_factor=1.0)
            add(
                "stock_daily_basic",
                trade_date=day,
                ts_code=code,
                close=20.0,
                total_mv=100.0,
                circ_mv=100.0,
            )
            add("stock_limit_daily", trade_date=day, ts_code=code, up_limit=22.0, down_limit=18.0)
        for code in ("000300.SH", "000001.SH"):
            add("index_daily", trade_date=day, ts_code=code, close=100.0, pre_close=100.0)
        for dataset in ("stock_st", "suspend_d"):
            quality += 1
            add(
                "data_quality_daily",
                id=quality,
                trade_date=day,
                dataset=dataset,
                status="PASS",
                expected_rows=0,
                actual_rows=0,
            )
    return {
        "tables": tables,
        "sequences": {
            "sector.sector_id": {"last_value": 1, "is_called": False, "increment": 1},
            "sector_member.id": {"last_value": 1, "is_called": True, "increment": 1},
            "data_quality_daily.id": {"last_value": 600, "is_called": True, "increment": 1},
        },
        "fixture_sha": schema["sources"]["tests/integration/test_business_recalc_performance.py"][
            "sha256"
        ],
        "catalog": input_catalog(schema),
    }


class FrozenSeed:
    @classmethod
    def capture_once(cls, generator):
        require(callable(generator), "SEED_CAPTURE_REQUIRED")
        return cls(generator())

    def __init__(self, captured_entity):
        self._source = deepcopy(captured_entity)
        self._manifest = self._capture(self._source)
        self._plans, self._observations = {}, []

    @staticmethod
    def _capture(entity):
        require(
            type(entity) is dict
            and set(entity) == {"tables", "sequences", "fixture_sha", "catalog"},
            "SEED_ENTITY_REQUIRED",
        )
        reference, _ = original_fixture_oracle()
        require(entity["fixture_sha"] == reference["fixture_sha"], "SEED_OLD_SOURCE")
        require(entity["catalog"] == reference["catalog"], "SEED_CATALOG_DRIFT")
        manifest = snapshot_input_rows(recipe_template(), entity["tables"], entity["sequences"])
        # All values including defaults are pinned, not just the old partial value checks.
        require(entity_digest(entity) == entity_digest(reference), "SEED_ENTITY_MISMATCH")
        return {
            "tables": manifest["tables"],
            "sequences": entity["sequences"],
            "catalog_sha256": sha(entity["catalog"]),
            "entity_sha256": entity_digest(entity),
            "fixture_sha256": entity["fixture_sha"],
            "source": source_identity(),
            "rows": sum(len(x) for x in entity["tables"].values()),
            "owner_selection": "NOT_SELECTED",
            "real_input_equal": False,
        }

    def prepare_manifest(self):
        require(self._capture(self._source) == self._manifest, "SEED_SOURCE_TAMPERED")
        return deepcopy(self._manifest)

    def plan_load(self, arm, loader_id, physical_resource):
        require(arm in ("OFF1", "ON1") and arm not in self._plans, "SEED_ARM_REPLAY")
        label(loader_id)
        label(physical_resource)
        require(
            all(
                p["loader_id"] != loader_id and p["resource"] != physical_resource
                for p in self._plans.values()
            ),
            "SEED_RESOURCES_NOT_INDEPENDENT",
        )
        plan = {
            "arm": arm,
            "loader_id": loader_id,
            "resource": physical_resource,
            "manifest_sha256": sha(self.prepare_manifest()),
        }
        self._plans[arm] = deepcopy(plan)
        return plan

    def verify_loaded_snapshot(self, plan, reader):
        require(plan == self._plans.get(plan.get("arm")), "SEED_PLAN_UNKNOWN")
        require(callable(reader), "SEED_ENTITY_READER_REQUIRED")
        observed = self._capture(reader(deepcopy(plan)))
        require(observed == self.prepare_manifest(), "SEED_LOADED_ENTITY_MISMATCH")
        result = {
            "plan": deepcopy(plan),
            "observed_sha256": sha(observed),
            "evidence_kind": "FAKE_ENTITY_OBSERVATION",
            "real_input_equal": False,
        }
        self._observations.append(result)
        return result

    def compare_loaded(self, left, right):
        require(
            any(left is x for x in self._observations)
            and any(right is x for x in self._observations),
            "SEED_OBSERVATION_UNKNOWN",
        )
        require(
            left["plan"]["arm"] == "OFF1"
            and right["plan"]["arm"] == "ON1"
            and left["observed_sha256"] == right["observed_sha256"],
            "SEED_PAIR_MISMATCH",
        )
        return {"fake_entity_bytes_equal": True, "real_input_equal": False, "G05": "MISSING"}

    load_real = staticmethod(deny_real)
