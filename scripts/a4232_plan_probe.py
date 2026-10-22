"""Untimed safe plan signatures, keeping driver preparation and binds separate."""

import hashlib
import re

from scripts import publication_lookup_diagnostic_a422 as lab
from scripts.a42_artifacts import now
from scripts.a42_receipt_contract import require
from scripts.a4232_stability_contract import TEMPLATE_HASHES, plan_structure
from scripts.publication_lookup_tail_attribution_a4231 import digest

BIND = re.compile(r'(?<!:):([a-z_]+)')


def parameterize(statement):
    order = []
    def replace(match):
        name = match[1]
        if name not in order:
            order.append(name)
        return '$'+str(order.index(name)+1)
    server = BIND.sub(replace, statement)
    require(order == ['keys','publication','table_name'], 'A4232_PARAMETER_ORDER_CHANGED')
    driver = BIND.sub(lambda m:'%('+m[1]+')s',statement)
    return server, driver, order


def capture_queries(ws, model, inputs):
    class Captured(Exception):
        pass
    result = {}
    for variant in ('C0','C1'):
        captured = []
        def observer(statement, parameters, captured=captured):
            captured.append((statement,parameters))
            raise Captured()
        try:
            lab.lookup(ws, model, inputs[:500], variant, observer=observer)
        except Captured:
            pass
        require(len(captured) == 1, 'A4232_QUERY_CAPTURE_FAILED')
        statement, params = captured[0]
        require(hashlib.sha256(statement.encode()).hexdigest() == TEMPLATE_HASHES[variant],
                'A4232_SQL_TEMPLATE_CHANGED')
        server, driver, order = parameterize(statement)
        require(set(params) == set(order), 'A4232_PARAMETERS_CHANGED')
        # All values below remain in memory; output only hashes and plan structures.
        result[variant] = dict(driver=driver, params=params, order=order,
                              server_sha256=hashlib.sha256(server.encode()).hexdigest())
    return result


def prepared_rows(db):
    from sqlalchemy import text

    return [dict(r) for r in db.execute(text('SELECT name,statement,generic_plans,custom_plans,'
        "parameter_types::text FROM pg_prepared_statements "
        "WHERE statement LIKE 'WITH input_keys AS%%'"))
        .mappings()]


def driver(db):
    return db.connection().connection.driver_connection


def fresh_snapshot(probe, queries):
    result = {}
    for variant,query in queries.items():
        with driver(probe).cursor() as cursor:
            cursor.execute('EXPLAIN (FORMAT JSON) '+query['driver'],query['params'],prepare=False)
            structure = plan_structure(cursor.fetchone()[0][0]['Plan'])
        result[variant] = dict(structure=structure,sha256=digest(structure))
    return result


def plan_snapshot(db, probe, queries):
    from psycopg import sql

    raw_driver = driver(db)
    require(raw_driver.prepare_threshold == 5 and raw_driver.prepared_max == 100,
            'A4232_DRIVER_PREPARATION_POLICY_CHANGED')
    result = dict(observed_at=now(), variants={}, prepare_threshold=5, prepared_max=100)
    fresh_plans = fresh_snapshot(probe,queries)
    for variant, query in queries.items():
        fresh = fresh_plans[variant]['structure']
        before = [r for r in prepared_rows(db)
                  if hashlib.sha256(r['statement'].encode()).hexdigest()
                  == query['server_sha256']]
        require(len(before) == 1, 'A4232_PREPARED_IDENTITY_MISSING')
        item = before[0]
        # EXECUTE is a utility statement: driver Literal adapts values safely;
        # the composed statement/values and unsanitized plan are NEVER exported.
        command = sql.SQL('EXPLAIN (FORMAT JSON) EXECUTE {}({})').format(
            sql.Identifier(item['name']), sql.SQL(',').join(
                sql.Literal(query['params'][name]) for name in query['order']))
        with raw_driver.cursor() as cursor:
            cursor.execute(command, prepare=False)
            cached = plan_structure(cursor.fetchone()[0][0]['Plan'])
        after = next(r for r in prepared_rows(db) if r['name'] == item['name'])
        changes = {k:after[k]-item[k] for k in ('generic_plans','custom_plans')}
        require(changes in (dict(generic_plans=1,custom_plans=0),
                            dict(generic_plans=0,custom_plans=1)),
                'A4232_PREPARED_MODE_NOT_OBSERVED')
        mode = 'generic' if changes['generic_plans'] else 'custom'
        result['variants'][variant] = dict(fresh_structure=fresh,fresh_sha256=digest(fresh),
            cached_structure=cached,cached_sha256=digest(cached),cached_mode=mode,
            server_sql_sha256=query['server_sha256'],name_sha256=digest(item['name']),
            parameter_types_sha256=digest(item['parameter_types']),
            generic_plans=after['generic_plans'],custom_plans=after['custom_plans'])
    return result


def plan_identity(value):
    require(set(value.get('variants',{})) == {'C0','C1'}, 'A4232_PLAN_MISSING')
    return {v:{k:values[k] for k in ('fresh_sha256','cached_sha256','cached_mode',
                'server_sql_sha256','parameter_types_sha256')}
            for v,values in value['variants'].items()}


def assert_plans(expected, actual):
    if plan_identity(expected) != plan_identity(actual):
        error = ValueError('A4232_ENVIRONMENT_DRIFT')
        error.a4232_drift = dict(plan_before=expected,plan_after=actual)
        raise error
