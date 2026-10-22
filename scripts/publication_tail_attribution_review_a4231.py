"""Offline review of the sole pinned diagnostic ZIP, never a new experiment."""

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.a42_artifacts import atomic  # noqa: E402
from scripts.a42_receipt_contract import physical, require  # noqa: E402
from scripts.a4231_attribution_metrics import schedule, summarize, telemetry_checks  # noqa: E402
from scripts.publication_lookup_tail_attribution_a4231 import (  # noqa: E402
    CONTROL,
    PROTOCOL_SHA256,
    VERSION,
)
from scripts.publication_lookup_tail_review_a423 import (  # noqa: E402
    C0_SOURCE,
    C1_SOURCE,
    INPUT_HASHES,
)

SOURCE_SHA = "947966dc5a33cc6d8a688431f6deb00a2dffa538"
SOURCE_RUN = "39820748153"
SOURCE_ARTIFACT = 12444391989
ZIP_SHA256 = "8457f553e548b4306c5d402cc86e8ea3afe3c754e1a34a80e47fc089796b9bcf"
STATS_FIELDS = ("reltuples", "relpages", "last_analyze", "last_autoanalyze")


def statistics_drift(expected, observed):
    """Planner statistics are not frozen by importing a data MVCC snapshot."""
    left = {t['relname']:t for t in expected['environment']['tables']}
    right = {t['relname']:t for t in observed['environment']['tables']}
    require(len(left) == len(right) == 4 and set(left) == set(right),
            'A4231_REVIEW_STATISTICS_TABLES_MISSING')
    require(expected['index_definition_sha256'] == observed['index_definition_sha256']
            and expected['settings_sha256'] == observed['settings_sha256'],
            'A4231_REVIEW_INDEX_OR_SETTINGS_DRIFT')
    result = []
    for name in sorted(left):
        for field in STATS_FIELDS:
            require(field in left[name] and field in right[name],
                    'A4231_REVIEW_STATISTICS_FIELD_MISSING')
            if left[name][field] != right[name][field]:
                result.append(dict(table=name, field=field, before=left[name][field],
                                   after=right[name][field]))
    return result


def classification(drift, checks):
    # Neither a successful collector nor a positive screen grants admission.
    return dict(collection_status='COMPLETE',
        analysis_status='INCOMPLETE_ENVIRONMENT_DRIFT' if drift else 'REVIEWED_DIAGNOSTIC_ONLY',
        root_cause='INSUFFICIENT_EVIDENCE' if drift or not checks[
            'all_preregistered_conditions_met'] else 'REQUIRES_MANUAL_CAUSAL_REVIEW',
        unique_repair_candidate=None, capacity_ready=False, performance_eligible=False,
        production_read_authorized=False, p2='NOT_AUTHORIZED', p3='NOT_AUTHORIZED',
        excluded_samples=0, repeated_experiments=0)


def review(archive):
    require(archive.stat().st_size < 5_000_000, 'A4231_REVIEW_ARCHIVE_TOO_LARGE')
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == ZIP_SHA256,
            'A4231_REVIEW_ZIP_DIGEST_MISMATCH')
    with ZipFile(archive) as z:
        names = {'attribution.json', 'tests.xml'} | {
            f'child-{r}-{b}.json' for r in ('as_seeded', 'analyzed') for b in (0, 1)}
        require(len(z.namelist()) == 6 and set(z.namelist()) == names
                and all(i.file_size < 10_000_000 for i in z.infolist()),
                'A4231_REVIEW_ARCHIVE_MEMBERS_INVALID')
        parent = json.loads(z.read('attribution.json'))
        physical(parent)
        require(parent['head_sha'] == SOURCE_SHA and parent['run_id'] == SOURCE_RUN
                and parent['attempt'] == '1' and parent['working_tree_dirty'] is False
                and parent['status'] == 'COMPLETE' and parent['evidence_kind'] == 'DIAGNOSTIC_ONLY'
                and parent['measurement_version'] == VERSION
                and parent['protocol_sha256'] == PROTOCOL_SHA256
                and parent['production_source_sha256'] == C0_SOURCE
                and parent['proposed_source_sha256'] == C1_SOURCE
                and sum(parent['public_counts'].values()) == 603040
                and sum(parent['candidate_counts'].values()) == 503020,
                'A4231_REVIEW_PARENT_IDENTITY_INVALID')
        drift, children, rows, snapshots = [], [], [], {}
        for member in parent['children']:
            raw = z.read(member['file'])
            require(hashlib.sha256(raw).hexdigest() == member['sha256'],
                    'A4231_REVIEW_CHILD_DIGEST_MISMATCH')
            child = json.loads(raw)
            physical(child)
            for field in ('head_sha', 'run_id', 'attempt', 'model_hash', 'protocol_sha256',
                          'database_instance', 'physical_system_identifier',
                          'production_source_sha256', 'measurement_version', 'sql_template_sha256'):
                require(child[field] == parent[field], 'A4231_REVIEW_CHILD_IDENTITY_INVALID')
            for receipt in (parent, child):
                require(receipt['capacity_ready'] is False
                        and receipt['performance_eligible'] is False
                        and receipt['production_read_authorized'] is False
                        and receipt['p2'] == receipt['p3'] == 'NOT_AUTHORIZED',
                        'A4231_REVIEW_UNAUTHORIZED_CLAIM')
            regime, block = member['statistics'], member['block']
            require(child['status'] == 'COMPLETE' and child['working_tree_dirty'] is False
                    and child['input_key_sha256'] == INPUT_HASHES[CONTROL]
                    and [(s['round'],s['position'],s['variant'],s['observer_mode'])
                         for s in child['samples']] == schedule(block)
                    and all(s['keys'] == 2000 and s['batch_size'] == 500 and s['golden'] == 'PASS'
                            and s['statistics'] == regime and s['block'] == block
                            and s['process_pid'] == child['process_pid'] for s in child['samples']),
                    'A4231_REVIEW_CHILD_COHORT_INVALID')
            snapshot = child['parent_snapshot_sha256']
            require(snapshots.setdefault(regime, snapshot) == snapshot,
                    'A4231_REVIEW_SNAPSHOT_MISMATCH')
            for phase in ('before', 'after'):
                differences = statistics_drift(parent['environments'][regime],
                                                child['environment_'+phase])
                if differences:
                    drift.append(dict(statistics=regime, block=block, phase=phase,
                                      differences=differences))
            children.append(member | dict(snapshot_sha256=snapshot,
                input_key_sha256=child['input_key_sha256'],
                index_sha256=child['environment_before']['index_definition_sha256'],
                settings_sha256=child['environment_before']['settings_sha256']))
            rows.extend(child['samples'])
        require(rows == parent['samples'] and len(rows) == 128
                and len({c['process_pid'] for c in children}) == 4
                and [(c['statistics'], c['block']) for c in children]
                    == [(r,b) for r in ('as_seeded','analyzed') for b in (0,1)],
                'A4231_REVIEW_COHORT_INCOMPLETE')
        require(all(math.isfinite(s['wall_seconds']) and s['wall_seconds'] > 0 for s in rows),
                'A4231_REVIEW_INVALID_WALL')
        groups, checks = summarize(rows), telemetry_checks(rows)
        require(groups == parent['summary'] and checks == parent['h3_preregistered_checks'],
                'A4231_REVIEW_QUANTILES_CHANGED')
        suites = [dict(s.attrib) for s in ElementTree.fromstring(z.read('tests.xml'))
                  .iter('testsuite')]
        require(sum(int(s['tests']) for s in suites) == 85
                and all(int(s[k]) == 0 for s in suites for k in ('failures','errors','skipped')),
                'A4231_REVIEW_PREFLIGHT_NOT_PASS')
    components, gen2 = [], []
    for group in groups:
        selected = [s for s in rows if all(s[k] == group[k]
                    for k in ('statistics', 'variant', 'observer_mode'))]
        components.append({k:group[k] for k in ('statistics','variant','observer_mode')} | dict(
            metric_medians={k:statistics.median(s['metrics'][k] for s in selected)
                for k in ('execute_seconds','python_json_seconds',
                          'buffered_row_materialization_seconds','gc_seconds')},
            client_cpu_median=statistics.median(s['client_cpu_seconds'] for s in selected),
            rss_after_exit_max=max(s['memory_after_exit']['current_rss_bytes'] for s in selected)))
    for row in rows:
        for event in row['gc_events']:
            if event['generation'] == 2:
                gen2.append({k:row[k] for k in ('statistics','block','round','position','variant',
                    'observer_mode','wall_seconds','client_cpu_seconds','metrics')}
                    | dict(event=event))
    return dict(schema_version='a4231-offline-review-v1', source_sha=SOURCE_SHA,
        source_run_id=SOURCE_RUN, source_attempt=1, source_artifact_id=SOURCE_ARTIFACT,
        source_zip_sha256=ZIP_SHA256, protocol_sha256=PROTOCOL_SHA256,
        evidence_kind='DIAGNOSTIC_ONLY_NOT_PERFORMANCE_ACCEPTANCE',
        **classification(drift, checks), sample_count=128, children=children,
        statistics_drift=drift, groups=groups, component_medians=components,
        generation2_events=gen2, h3_preregistered_checks=checks, preflight_junit=suites,
        caveat='No GC subtraction, no cross-version gain, no automatic repair/capacity admission')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'A4231_REVIEW_OUTPUT_EXISTS')
    atomic(args.output, review(args.archive))


if __name__ == '__main__':
    main()
