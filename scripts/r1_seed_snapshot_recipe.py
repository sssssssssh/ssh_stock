"""Pure offline R1 seed recipes. No seed/ORM/DB import and no loading actions."""

import hashlib
from copy import deepcopy
from datetime import date, datetime, timedelta

from scripts.r1_business_snapshot_contract import load_schema
from scripts.r1_real_root_protocol import BASELINE, FIXTURE, digest, exact, require

SCHEMA = "r1.seed-recipe.v1"
METHODS = ("BASELINE_SNAPSHOT_ONCE_THEN_LOAD_TWICE", "EXPLICIT_PER_ARM_TIMESTAMP_MAPPING")
FROZEN_COLUMNS = {
    "stock_basic.updated_at",
    "stock_daily.source_updated_at",
    "stock_limit_daily.created_at",
    "stock_limit_daily.updated_at",
    "data_quality_daily.checked_at",
}


def expected_counts():
    """Arithmetic from the original weekday-only loop, never database observations."""
    return {
        "stock_basic": 2,
        "trade_calendar": 420,
        "stock_daily": 600,
        "stock_adj_factor": 600,
        "stock_daily_basic": 600,
        "stock_limit_daily": 600,
        "index_daily": 600,
        "stock_st_daily": 0,
        "stock_suspend_daily": 0,
        "sector": 1,
        "sector_member": 1,
        "data_quality_daily": 600,
        **{
            n: 0
            for n in (
                "theme",
                "theme_member_snapshot",
                "theme_member_interval",
                "theme_daily",
                "theme_moneyflow_daily",
                "theme_limit_daily",
            )
        },
    }


def recipe_template(method=METHODS[0]):
    require(method in METHODS, "R1_RECIPE_METHOD")
    schema = load_schema()
    timestamps = []
    for table, spec in schema["tables"].items():
        for column, rule in spec["columns"].items():
            if rule["type"] != "datetime":
                continue
            timestamps.append(
                {
                    "table": table,
                    "column": column,
                    "source": rule["source"],
                    "role": "SEED_INPUT"
                    if table + "." + column in FROZEN_COLUMNS
                    else "ROOT_RUNTIME"
                    if rule["policy"] == "TIMESTAMP_EVENT_MAPPING"
                    else "EVIDENCE",
                    "freeze": "DECISION_REQUIRED",
                    "timezone": "UTC",
                    "precision": "microsecond",
                }
            )
    return {
        "schema_version": SCHEMA,
        "target_sha": BASELINE,
        "fixture": deepcopy(FIXTURE),
        "method": method,
        "owner_selection": "NOT_SELECTED",
        "decision": "DECISION_REQUIRED",
        "timestamp_columns": timestamps,
        "calendar": {
            "start": "2025-01-01",
            "end": "2026-02-24",
            "weekday_only": True,
            "indices": ["000300.SH", "000001.SH"],
        },
        "delisted": {
            "ts_code": "000002.SZ",
            "list_date": "2025-01-11",
            "delist_date": "2025-01-26",
            "list_status": "D",
        },
        "quality_inputs": ["stock_st", "suspend_d"],
        "strategy_sha256": schema["sources"]["config/strategy.yaml"]["sha256"],
        "sequence_policy": "EXPLICIT_ALL_SERIAL_SEQUENCE_STATES_AND_RANDOM_GENERATOR_STATE",
        "G05": "MISSING",
        "G08": "PARTIAL",
        "real_load_authorized": False,
    }


def validate_recipe(value):
    require(type(value) is dict, "R1_RECIPE_FIELDS")
    exact(value, recipe_template(value.get("method")))
    require(len(value["timestamp_columns"]) == 49, "R1_RECIPE_TIMESTAMPS")
    return {
        "status": "OFFLINE_RECIPE_VALID",
        "decision": "DECISION_REQUIRED",
        "G05": "MISSING",
        "G08": "PARTIAL",
        "real_input_equal": False,
    }


def frozen_manifest(recipe, *, schema_sha256, ordered_tables, sequence_states, random_state):
    """Metadata for an independently exported common synthetic input, not a dump."""
    validate_recipe(recipe)
    schema = load_schema()
    expected = {t for t, spec in schema["tables"].items() if spec["domain"] == "INPUT"}
    require(type(ordered_tables) is dict and set(ordered_tables) == expected, "R1_SEED_TABLES")
    from scripts.r1_business_snapshot_contract import SCHEMA_SHA256

    require(schema_sha256 == SCHEMA_SHA256, "R1_SCHEMA_DRIFT")
    for table, entry in ordered_tables.items():
        require(
            type(entry) is dict
            and set(entry)
            == {
                "sha256",
                "rows",
                "columns",
                "type_hash",
                "non_timestamp_sha256",
                "timestamp_values",
            },
            "R1_SEED_MANIFEST",
        )
        require(entry["columns"] == list(schema["tables"][table]["columns"]), "R1_SEED_COLUMNS")
        require(
            type(entry["rows"]) is int and entry["rows"] == expected_counts()[table], "R1_SEED_ROWS"
        )
        require(
            entry["type_hash"]
            == digest(
                {
                    c: {"type": v["type"], "nullable": v["nullable"]}
                    for c, v in schema["tables"][table]["columns"].items()
                }
            ),
            "R1_SEED_TYPE_HASH",
        )
        for field in ("sha256", "type_hash", "non_timestamp_sha256"):
            v = entry[field]
            require(
                type(v) is str and len(v) == 64 and all(c in "0123456789abcdef" for c in v),
                "R1_SEED_HASH",
            )
        timestamp_columns = {x.split(".")[1] for x in FROZEN_COLUMNS if x.startswith(table + ".")}
        require(
            type(entry["timestamp_values"]) is dict
            and set(entry["timestamp_values"]) == timestamp_columns,
            "R1_SEED_TIMESTAMPS",
        )
        for vector in entry["timestamp_values"].values():
            require(type(vector) is list and len(vector) == entry["rows"], "R1_SEED_TIMESTAMPS")
            for text in vector:
                require(
                    type(text) is str and len(text) == 27 and text.endswith("Z"),
                    "R1_SEED_TIMESTAMPS",
                )
                try:
                    time = datetime.fromisoformat(text)
                except ValueError:
                    require(False, "R1_SEED_TIMESTAMPS")
                require(time.utcoffset() == timedelta(0), "R1_SEED_TIMESTAMPS")
    # Serial IDs are not dropped: manifest must enumerate every seed input serial.
    serials = {
        f"{t}.{c}"
        for t, spec in schema["tables"].items()
        if t in expected
        for c, rule in spec["columns"].items()
        if "autoincrement=True" in rule["source"]["declaration"]
    }
    require(type(sequence_states) is dict and set(sequence_states) == serials, "R1_SEQUENCE_SET")
    for state in sequence_states.values():
        require(
            type(state) is dict
            and set(state) == {"last_value", "is_called", "increment"}
            and type(state["last_value"]) is int
            and type(state["is_called"]) is bool
            and type(state["increment"]) is int
            and state["increment"] == 1,
            "R1_SEQUENCE",
        )
    require(
        type(random_state) is dict
        and set(random_state) == {"algorithm", "state_sha256"}
        and random_state["algorithm"] == "ORIGINAL_SEED_NO_RANDOM_CALLS",
        "R1_RANDOM_STATE",
    )
    require(random_state["state_sha256"] == digest({"random_calls": 0}), "R1_RANDOM_STATE")
    return {
        "schema_version": "r1.seed-frozen-manifest.v1",
        "evidence_kind": "SYNTHETIC_ONLY",
        "recipe_sha256": digest(recipe),
        "schema_sha256": schema_sha256,
        "tables": deepcopy(ordered_tables),
        "sequences": deepcopy(sequence_states),
        "random": deepcopy(random_state),
        "real_export_verified": False,
    }


def snapshot_input_rows(recipe, tables, sequence_states):
    """Consume all original R1 typed input columns in memory, with native row checks.

    IDs and sequence states remain values. In particular explicitly inserting
    Sector(101) does not imply its sequence has advanced to 101.
    """
    from scripts.r1_business_snapshot_contract import SCHEMA_SHA256, check_type, frame

    validate_recipe(recipe)
    schema = load_schema()
    require(type(tables) is dict and set(tables) == set(expected_counts()), "R1_SEED_TABLES")
    manifest = {}
    for table, rows in tables.items():
        require(type(rows) is list and len(rows) == expected_counts()[table], "R1_SEED_ROWS")
        spec = schema["tables"][table]
        ordered, seen, seen_pk = [], set(), set()
        time_columns = [
            x.split(".")[1] for x in sorted(FROZEN_COLUMNS) if x.startswith(table + ".")
        ]
        for row in rows:
            require(type(row) is dict and set(row) == set(spec["columns"]), "R1_SEED_COLUMNS")
            for column, value in row.items():
                check_type(value, spec["columns"][column])
            key = frame(tuple(row[c] for c in spec["natural_key"]))
            require(key not in seen, "R1_SEED_DUPLICATE_KEY")
            seen.add(key)
            pk = frame(tuple(row[c] for c in spec["primary_key"]))
            require(pk not in seen_pk, "R1_SEED_DUPLICATE_PK")
            seen_pk.add(pk)
            check_original_values(table, row)
            non_time = {k: v for k, v in row.items() if k not in time_columns}
            ordered.append(
                (
                    key,
                    frame(row),
                    frame(non_time),
                    {c: row[c].strftime("%Y-%m-%dT%H:%M:%S.%fZ") for c in time_columns},
                )
            )
        sha, semantic = hashlib.sha256(), hashlib.sha256()
        times = {c: [] for c in time_columns}
        sha.update(frame([table, list(spec["columns"]), len(rows)]))
        for _, raw, non_time, stamps in sorted(ordered):
            sha.update(raw)
            semantic.update(non_time)
            for c, value in stamps.items():
                times[c].append(value)
        manifest[table] = {
            "sha256": sha.hexdigest(),
            "rows": len(rows),
            "columns": list(spec["columns"]),
            "non_timestamp_sha256": semantic.hexdigest(),
            "timestamp_values": times,
            "type_hash": digest(
                {
                    c: {"type": v["type"], "nullable": v["nullable"]}
                    for c, v in spec["columns"].items()
                }
            ),
        }
        for col, rule in spec["columns"].items():
            if rows and "autoincrement=True" in rule["source"]["declaration"] and table != "sector":
                state = sequence_states.get(table + "." + col, {})
                require(
                    state.get("is_called") is True
                    and type(state.get("last_value")) is int
                    and state["last_value"] >= max(row[col] for row in rows),
                    "R1_SEQUENCE",
                )
    return frozen_manifest(
        recipe,
        schema_sha256=SCHEMA_SHA256,
        ordered_tables=manifest,
        sequence_states=sequence_states,
        random_state={
            "algorithm": "ORIGINAL_SEED_NO_RANDOM_CALLS",
            "state_sha256": digest({"random_calls": 0}),
        },
    )


def check_original_values(table, row):
    start, end = date(2025, 1, 1), date(2026, 2, 24)
    day = row.get("trade_date")
    if day is not None:
        require(start <= day <= end and day.weekday() < 5, "R1_SEED_DAY")
    if "ts_code" in row:
        allowed = (
            ("000300.SH", "000001.SH") if table == "index_daily" else ("000001.SZ", "000002.SZ")
        )
        require(row["ts_code"] in allowed, "R1_SEED_SYMBOL")
    expected = {}
    if table == "stock_basic":
        closed = row["ts_code"] == "000002.SZ"
        expected = {
            "list_date": start + timedelta(days=10) if closed else start,
            "delist_date": start + timedelta(days=25) if closed else None,
            "exchange": "SZSE",
            "list_status": "D" if closed else "L",
        }
    elif table == "trade_calendar":
        require(start <= row["cal_date"] <= end, "R1_SEED_DAY")
        expected = {"is_open": row["cal_date"].weekday() < 5}
    elif table == "stock_daily":
        expected = {
            "close": 20.0,
            "open": 20.0,
            "high": 21.0,
            "low": 19.0,
            "vol": 100000.0,
            "amount": 1000000.0,
        }
    elif table == "stock_adj_factor":
        expected = {"adj_factor": 1.0}
    elif table == "stock_daily_basic":
        expected = {"close": 20.0, "total_mv": 100.0, "circ_mv": 100.0}
    elif table == "stock_limit_daily":
        expected = {"up_limit": 22.0, "down_limit": 18.0}
    elif table == "index_daily":
        expected = {"close": 100.0, "pre_close": 100.0}
    elif table == "sector":
        expected = {
            "sector_id": 101,
            "source": "SW",
            "source_code": "BIZ",
            "name": "synthetic",
            "level": "L1",
        }
    elif table == "sector_member":
        expected = {"sector_id": 101, "ts_code": "000001.SZ", "valid_from": start}
    elif table == "data_quality_daily":
        require(row["dataset"] in ("stock_st", "suspend_d"), "R1_SEED_QUALITY")
        expected = {"status": "PASS", "expected_rows": 0, "actual_rows": 0, "job_id": None}
    for column, value in expected.items():
        require(type(row[column]) is type(value) and row[column] == value, "R1_SEED_VALUE")


def compare_load_recipes(recipe, baseline, left, right, event_mapping=None):
    """Validate two independent *offline* consumers against frozen metadata.

    Source payload hashes/row counts/types/serials are exact. A per-arm timestamp
    mapping may establish semantic correspondence, never raw input byte equality.
    """
    validate_recipe(recipe)
    require(
        type(baseline) is dict and baseline.get("evidence_kind") == "SYNTHETIC_ONLY",
        "R1_SEED_MANIFEST",
    )
    rebuilt = frozen_manifest(
        recipe,
        schema_sha256=baseline.get("schema_sha256"),
        ordered_tables=baseline.get("tables"),
        sequence_states=baseline.get("sequences"),
        random_state=baseline.get("random"),
    )
    exact(baseline, rebuilt)
    for arm, consumer in (("OFF1", left), ("ON1", right)):
        require(
            type(consumer) is dict
            and set(consumer)
            == {"arm", "loader_ref", "source_manifest_sha256", "observed_manifest"},
            "R1_LOADER",
        )
        require(consumer["arm"] == arm and type(consumer["loader_ref"]) is str, "R1_LOADER")
        require(consumer["source_manifest_sha256"] == digest(baseline), "R1_SEED_SOURCE")
        if recipe["method"] == METHODS[0]:
            exact(consumer["observed_manifest"], baseline)
        else:
            observed = consumer["observed_manifest"]
            regenerated = frozen_manifest(
                recipe,
                schema_sha256=observed.get("schema_sha256"),
                ordered_tables=observed.get("tables"),
                sequence_states=observed.get("sequences"),
                random_state=observed.get("random"),
            )
            exact(regenerated, observed)
            projected = deepcopy(observed)
            for table, entry in baseline["tables"].items():
                if entry["timestamp_values"]:
                    projected["tables"][table]["sha256"] = entry["sha256"]
                    projected["tables"][table]["timestamp_values"] = entry["timestamp_values"]
            exact(projected, baseline)
    require(left["loader_ref"] != right["loader_ref"], "R1_LOADERS_NOT_INDEPENDENT")
    if recipe["method"] == METHODS[1]:
        require(
            type(event_mapping) is dict and set(event_mapping) == FROZEN_COLUMNS,
            "R1_SEED_EVENT_MAPPING",
        )
        for name, values in event_mapping.items():
            require(
                type(values) is dict and set(values) == {"left_raw", "right_raw", "pairs"},
                "R1_SEED_EVENT_MAPPING",
            )
            require(
                type(values["left_raw"]) is str
                and type(values["right_raw"]) is str
                and len(values["left_raw"]) == len(values["right_raw"]) == 64,
                "R1_SEED_EVENT_MAPPING",
            )
            require(
                type(values["pairs"]) is list and bool(values["pairs"]), "R1_SEED_EVENT_MAPPING"
            )
            from scripts.r1_business_snapshot_contract import IdentityMap

            identities = IdentityMap(
                {"job": [], "token": [], "scope": [], "events": values["pairs"]}
            )
            table, column = name.split(".")
            require(
                values["left_raw"] == left["observed_manifest"]["tables"][table]["sha256"]
                and values["right_raw"] == right["observed_manifest"]["tables"][table]["sha256"],
                "R1_SEED_EVENT_MAPPING",
            )
            for a, b in zip(
                left["observed_manifest"]["tables"][table]["timestamp_values"][column],
                right["observed_manifest"]["tables"][table]["timestamp_values"][column],
                strict=True,
            ):
                first, second = datetime.fromisoformat(a), datetime.fromisoformat(b)
                require(
                    identities.value("events", first, "left") == first
                    and identities.value("events", second, "right") == first,
                    "R1_SEED_EVENT_MAPPING",
                )
            identities.closed()
    return {
        "status": "OFFLINE_TWO_LOAD_RECIPES_VALID",
        "decision": "DECISION_REQUIRED",
        "synthetic_manifest_equal": True,
        "real_pg_input_equal": False,
        "raw_byte_equality_claim": False,
        "owner_selection": "NOT_SELECTED",
        "G05": "MISSING",
        "G08": "PARTIAL",
    }
