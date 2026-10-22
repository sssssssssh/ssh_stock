"""Offline forensic review of the sole source run, never a new measurement."""

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.a42_artifacts import atomic  # noqa: E402
from scripts.a42_receipt_contract import physical, require  # noqa: E402
from scripts.a4232_plan_probe import assert_plans, plan_identity  # noqa: E402
from scripts.a4232_stability_contract import (  # noqa: E402
    C0_SOURCE,
    C1_SOURCE,
    CONTROL,
    MODEL_HASH,
    PROTOCOL_HASH,
    VERSION,
    assert_counts,
    assert_stable,
    causal_checks,
    plan_structure,
    schedule,
    summarize,
)
from scripts.publication_lookup_tail_attribution_a4231 import digest  # noqa: E402
from scripts.publication_lookup_tail_review_a423 import INPUT_HASHES  # noqa: E402

SOURCE_SHA = '3916dc4dc72f83f2470a96ff265428bd2e9549e2'
SOURCE_RUN = '39833706083'


def validate_plan_hashes(plans):
    for value in plans['variants'].values():
        for kind in ('fresh','cached'):
            structure = value[kind+'_structure']
            require(structure == plan_structure(structure)
                    and digest(structure) == value[kind+'_sha256'],
                    'A4232_REVIEW_PLAN_HASH_MISMATCH')


def validate_complete(parent, children):
    physical(parent)
    assert_counts(parent['counts'])
    require(parent['model_hash'] == MODEL_HASH and parent['working_tree_dirty'] is False
            and parent['production_source_sha256'] == C0_SOURCE
            and parent['protocol_sha256'] == PROTOCOL_HASH
            and parent['measurement_version'] == VERSION,
            'A4232_REVIEW_SOURCE_CONTRACT_MISMATCH')
    expected = parent['stabilization']['identity']
    rows = []
    require([c['block'] for c in children] == list(range(4))
            and len({c['process_pid'] for c in children}) == 4, 'A4232_REVIEW_PROCESSES_MISSING')
    validate_plan_hashes(parent['frozen_plans'])
    for child in children:
        physical(child)
        for key in ('head_sha','run_id','attempt','model_hash','protocol_sha256',
                    'measurement_version','database_instance','physical_system_identifier'):
            require(child[key] == parent[key], 'A4232_REVIEW_CHILD_IDENTITY_MISMATCH')
        require(child['status'] == 'COMPLETE' and child['working_tree_dirty'] is False
                and child['input_key_sha256'] == INPUT_HASHES[CONTROL]
                and child['parent_snapshot_sha256'] == parent['parent_snapshot_sha256'],
                'A4232_REVIEW_CHILD_NOT_SAME_DATA_SNAPSHOT')
        for source in (parent,child):
            require(source['capacity_ready'] is False and source['performance_eligible'] is False
                    and source['production_matches_candidate'] is False
                    and source['production_read_authorized'] is False
                    and source['unique_repair_candidate'] is None
                    and source['p2'] == source['p3'] == 'NOT_AUTHORIZED',
                    'A4232_REVIEW_UNAUTHORIZED_CLAIM')
        block = child['block']
        require([(s['round'],s['position'],s['variant'],s['observer_mode'])
                 for s in child['samples']] == schedule(block)
                and [c['round'] for c in child['round_checks']] == list(range(8)),
                'A4232_REVIEW_COHORT_OR_ORDER_MISMATCH')
        warmups = (('C0','C1') if block % 2 == 0 else ('C1','C0'))*4
        require([w['variant'] for w in child['warmups']] == list(warmups)
                and all(w['keys'] == 2000 and w['observer_mode'] == 'none'
                        for w in child['warmups']), 'A4232_REVIEW_WARMUPS_CHANGED')
        assert_stable(expected,child['statistics_before_warmup'])
        snapshots = [child['initial_snapshot'],child['final_snapshot']]
        snapshots += [c[p] for c in child['round_checks'] for p in ('before','after')]
        for snap in snapshots:
            assert_stable(expected,snap['statistics'])
            validate_plan_hashes(snap['plans'])
            assert_plans(parent['frozen_plans'],snap['plans'])
        require(child['gc_initial']['gc_enabled'] == child['gc_final']['gc_enabled']
                and child['gc_initial']['gc_thresholds'] == child['gc_final']['gc_thresholds'],
                'A4232_REVIEW_GC_POLICY_CHANGED')
        for sample in child['samples']:
            require(sample['block'] == block and sample['process_pid'] == child['process_pid']
                    and sample['keys'] == 2000 and sample['batch_size'] == 500
                    and sample['golden'] == 'PASS' and len(sample['batch_seconds']) == 4
                    and math.isfinite(sample['wall_seconds']) and sample['wall_seconds'] > 0,
                    'A4232_REVIEW_SAMPLE_INVALID')
            check = child['round_checks'][sample['round']]
            for phase in ('before','after'):
                require(sample['round_plan_'+phase] == digest(plan_identity(check[phase]['plans'])),
                        'A4232_REVIEW_SAMPLE_PLAN_NOT_BOUND')
            for event in sample['gc_events']:
                require(event['generation'] in (0,1,2) and math.isfinite(event['seconds'])
                        and event['seconds'] >= 0 and isinstance(event['fully_inside_wall'],bool),
                        'A4232_REVIEW_GC_EVENTS_INVALID')
        rows.extend(child['samples'])
    require(len(rows) == 128 and rows == parent['samples'], 'A4232_REVIEW_ALL_SAMPLES_MISSING')
    require(summarize(rows) == parent['summary'] and causal_checks(rows) == parent['h3_checks'],
            'A4232_REVIEW_RECOMPUTATION_CHANGED')
    assert_stable(expected,parent['final_statistics'])
    return rows


def components(rows):
    groups = []
    for variant in ('C0','C1'):
        for mode in ('full','minimal'):
            selected = [s for s in rows if (s['variant'],s['observer_mode']) == (variant,mode)]
            if not selected:
                continue
            keys = ('execute_seconds','python_json_seconds',
                    'buffered_row_materialization_seconds','gc_seconds')
            groups.append(dict(variant=variant,observer_mode=mode,count=len(selected),
                metric_medians={k:statistics.median(s['metrics'][k] for s in selected)
                                for k in keys},
                client_cpu_median=statistics.median(s['client_cpu_seconds'] for s in selected),
                backend_cpu_interval_median=statistics.median(s['backend_after']['cpu_seconds']
                    - s['backend_before']['cpu_seconds'] for s in selected),
                rss_after_exit_max=max(s['memory_after_exit']['current_rss_bytes']
                                       for s in selected),
                gc_generations={str(g):dict(events=sum(e['generation'] == g for s in selected
                    for e in s['gc_events']),wall_events=sum(e['generation'] == g
                    and e['fully_inside_wall'] for s in selected for e in s['gc_events']))
                    for g in (0,1,2)}))
    return groups


def partial_audit(parent, children):
    """Describe independent fields, never relax the failed idle/cohort contract."""
    reference = parent.get('stabilization',{}).get('identity')
    result = dict(scope='DESCRIPTIVE_FIELD_AUDIT_NOT_ADMISSION',relation_field_changes=[],
        environment_field_changes=[],background_activity_changes=[],missing_plan_brackets=0,
        recorded_plan_snapshots=0,plan_identity_changes=[],child_statuses=[],
        parent_validated_samples=len(parent.get('samples',[])),physical_verified=False)
    if parent.get('isolation'):
        physical(parent)
        result['physical_verified'] = True
    for child in children:
        for field in ('head_sha','run_id','attempt','model_hash','protocol_sha256',
                      'measurement_version','database_instance','physical_system_identifier'):
            if field in parent:
                require(child.get(field) == parent[field],'A4232_REVIEW_CHILD_IDENTITY_MISMATCH')
        if child.get('isolation'):
            physical(child)
        block,rows = child['block'],child.get('samples',[])
        require(len(rows) <= 32 and [(r['round'],r['position'],r['variant'],r['observer_mode'])
            for r in rows] == schedule(block)[:len(rows)], 'A4232_REVIEW_PARTIAL_ORDER_MISMATCH')
        require(child['input_key_sha256'] == INPUT_HASHES[CONTROL]
                and child['parent_snapshot_sha256'] == parent['parent_snapshot_sha256']
                and all(r['keys'] == 2000 and r['batch_size'] == 500 and r['golden'] == 'PASS'
                        and math.isfinite(r['wall_seconds']) and r['wall_seconds'] > 0
                        for r in rows),
                'A4232_REVIEW_PARTIAL_SAMPLE_INVALID')
        result['child_statuses'].append(dict(block=block,status=child['status'],samples=len(rows)))
        result['missing_plan_brackets'] += sum(r.get('round_plan_after') is None for r in rows)
        points = [('before_warmup',dict(statistics=child['statistics_before_warmup']))]
        points += [(name,child[name]) for name in ('initial_snapshot','final_snapshot')
                   if name in child]
        points += [(f"round{r['round']}_{phase}",r[phase]) for r in child.get('round_checks',[])
                   for phase in ('before','after') if phase in r]
        if child.get('drift',{}).get('after'):
            points.append(('failure_after',dict(statistics=child['drift']['after'])))
        for phase,point in points:
            current = point['statistics']
            if reference is not None:
                expected = {r['relname']:r for r in reference['relations']}
                actual = {r['relname']:r for r in current['relations']}
                require(set(expected) == set(actual),'A4232_REVIEW_RELATIONS_MISSING')
                for name,row in actual.items():
                    for field,value in row.items():
                        if value != expected[name][field]:
                            result['relation_field_changes'].append(dict(block=block,phase=phase,
                                table=name,field=field,before=expected[name][field],after=value,
                                observed_at=current['observed_at']))
                for field in ('index_sha256','settings','planner_settings'):
                    if reference[field] != current[field]:
                        result['environment_field_changes'].append(dict(block=block,phase=phase,
                            field=field,before=reference[field],after=current[field]))
                if reference['active_autovacuum_workers'] != current['active_autovacuum_workers']:
                    result['background_activity_changes'].append(dict(block=block,phase=phase,
                        field='active_autovacuum_workers',before=reference['active_autovacuum_workers'],
                        after=current['active_autovacuum_workers'],observed_at=current['observed_at'],
                        target_table='NOT_AVAILABLE_COUNT_ONLY',operation='NOT_AVAILABLE'))
            if 'plans' in point:
                result['recorded_plan_snapshots'] += 1
                validate_plan_hashes(point['plans'])
                if plan_identity(point['plans']) != plan_identity(parent['frozen_plans']):
                    result['plan_identity_changes'].append(dict(block=block,phase=phase))
    return result


def review(archive, manifest):
    require(manifest.get('source_sha') == SOURCE_SHA and manifest.get('run_id') == SOURCE_RUN
            and manifest.get('attempt') == 1 and isinstance(manifest.get('artifact_id'),int),
            'A4232_REVIEW_MANIFEST_IDENTITY_MISMATCH')
    require(archive.stat().st_size < 10_000_000 and hashlib.sha256(archive.read_bytes()).hexdigest()
            == manifest.get('zip_sha256'), 'A4232_REVIEW_ZIP_DIGEST_MISMATCH')
    with ZipFile(archive) as z:
        allowed = {'attribution.json'} | {f'child-{b}.json' for b in range(4)}
        require(len(z.namelist()) == len(set(z.namelist())) and set(z.namelist()) <= allowed
                and 'attribution.json' in z.namelist()
                and all(i.file_size < 15_000_000 for i in z.infolist()),
                'A4232_REVIEW_ARCHIVE_MEMBERS_INVALID')
        parent = json.loads(z.read('attribution.json'))
        require(parent.get('head_sha') == SOURCE_SHA and parent.get('run_id') == SOURCE_RUN
                and parent.get('attempt') == '1', 'A4232_REVIEW_SOURCE_IDENTITY_MISMATCH')
        require(parent.get('model_hash') == MODEL_HASH and parent.get('working_tree_dirty') is False
                and parent.get('protocol_sha256') == PROTOCOL_HASH
                and parent.get('measurement_version') == VERSION
                and parent.get('production_source_sha256') == C0_SOURCE
                and parent.get('proposed_source_sha256') == C1_SOURCE,
                'A4232_REVIEW_SOURCE_CONTRACT_MISMATCH')
        children = [json.loads(z.read(f'child-{b}.json')) for b in range(4)
                    if f'child-{b}.json' in z.namelist()]
        for item in parent.get('children',[]):
            require(hashlib.sha256(z.read(item['file'])).hexdigest() == item['sha256'],
                    'A4232_REVIEW_CHILD_DIGEST_MISMATCH')
    complete = parent['status'] == 'COMPLETE'
    if children:
        assert_counts(parent['counts'])
    for value in (parent,*children):
        require(value.get('capacity_ready') is False and value.get('performance_eligible') is False
                and value.get('production_matches_candidate') is False
                and value.get('production_read_authorized') is False
                and value.get('unique_repair_candidate') is None
                and value.get('p2') == value.get('p3') == 'NOT_AUTHORIZED',
                'A4232_REVIEW_UNAUTHORIZED_CLAIM')
    rows = validate_complete(parent,children) if complete else [
        s for child in children for s in child.get('samples',[])]
    events = [{k:s[k] for k in ('block','round','position','variant','observer_mode',
        'wall_seconds','client_cpu_seconds','metrics')} | dict(event=e)
        for s in rows for e in s['gc_events'] if e['generation'] == 2]
    checks = causal_checks(rows) if complete else None
    result = dict(schema_version='a4232-offline-stability-review-v1',source_sha=SOURCE_SHA,
        source_run_id=SOURCE_RUN,source_attempt=1,source_artifact_id=manifest['artifact_id'],
        source_zip_sha256=manifest['zip_sha256'],evidence_kind='DIAGNOSTIC_ONLY',
        collection_status=parent['status'],sample_count=len(rows),excluded_samples=0,
        planned_samples=128,uncollected_samples=128-len(rows),
        source_started_at=parent.get('started_at'),source_finished_at=parent.get('finished_at'),
        statistics_plan_status='STABLE_BRACKETED' if complete else 'NOT_VERIFIED',
        root_cause='REQUIRES_MANUAL_CAUSAL_REVIEW' if checks and checks['all_met']
                   else 'INSUFFICIENT_EVIDENCE',unique_repair_candidate=None,
        capacity_ready=False,performance_eligible=False,production_matches_candidate=False,
        production_read_authorized=False,p2='NOT_AUTHORIZED',p3='NOT_AUTHORIZED',
        stabilization=parent.get('stabilization'),
        physical_identity={k:parent.get(k) for k in ('database_instance',
            'physical_system_identifier','postgres_version','model_hash','protocol_sha256')},
        final_statistics=parent.get('final_statistics'),frozen_plans=parent.get('frozen_plans'),
        summary=summarize(rows) if complete else [],component_medians=components(rows),
        generation2_events=events,h3_checks=checks,
        failed_samples=[dict(block=c.get('block'),sample=c['failed_sample'])
                        for c in children if 'failed_sample' in c],
        failures={k:parent[k] for k in ('first_failure','terminal_failure','drift','child_failure')
                  if k in parent},
        decision_caveat='Stable probes/collection alone never establish a unique production repair')
    if children:
        result['field_audit'] = partial_audit(parent,children)
    source_files = ('scripts/publication_tail_stability_a4232.py',
                    'scripts/a4232_stability_contract.py',
                    'scripts/a4232_plan_probe.py','scripts/publication_lookup_diagnostic_a422.py',
                    'scripts/a4231_attribution_metrics.py','backend/app/services/data_publication.py')
    result['source_hashes_reconstructed_from_git'] = {p:hashlib.sha256(subprocess.check_output(
        ['git','show',SOURCE_SHA+':'+p])).hexdigest() for p in source_files}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(not args.output.exists(),'A4232_REVIEW_OUTPUT_EXISTS')
    atomic(args.output,review(args.archive,json.loads(args.manifest.read_text())))


if __name__ == '__main__':
    main()
