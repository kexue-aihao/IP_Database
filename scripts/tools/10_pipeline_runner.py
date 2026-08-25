#!/usr/bin/env python3
"""
Subagent 10: Pipeline Runner — Phase 5

CI/CD pipeline script that orchestrates the full IP geolocation
improvement pipeline:
  1. Collect anchors
  2. Evaluate baseline
  3. Fetch and parse geofeed
  4. Run vote fusion
  5. Build high-precision MMDB
  6. Evaluate new database
  7. Generate report

Usage:
  python scripts/tools/10_pipeline_runner.py           # Full pipeline
  python scripts/tools/10_pipeline_runner.py --quick    # Skip slow steps
"""

import json
import os
import sys
import subprocess
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE, 'scripts')
TOOLS_DIR = os.path.join(SCRIPTS_DIR, 'tools')
OUTPUT_DIR = os.path.join(BASE, 'output')
REPORT_PATH = os.path.join(OUTPUT_DIR, 'pipeline_report.json')


def run_step(step_name, cmd, timeout=300):
    print(f'\n=== Step: {step_name} ===')
    print(f'  Running: {cmd}')
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f'  [FAILED] exit code {result.returncode}')
            print(f'  stderr: {result.stderr[:500]}')
            return {'step': step_name, 'status': 'failed', 'stderr': result.stderr[:500]}
        print(f'  [OK]')
        return {'step': step_name, 'status': 'ok', 'stdout': result.stdout[:1000]}
    except subprocess.TimeoutExpired:
        print(f'  [TIMEOUT] exceeded {timeout}s')
        return {'step': step_name, 'status': 'timeout'}
    except Exception as e:
        print(f'  [ERROR] {e}')
        return {'step': step_name, 'status': 'error', 'message': str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run full IP precision pipeline')
    parser.add_argument('--quick', action='store_true', help='Skip slow steps')
    args = parser.parse_args()

    print('=' * 60)
    print('IP Geolocation Precision Pipeline')
    print(f'Started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)

    results = []

    # Step 1: Collect anchors
    results.append(run_step('Anchor Collection',
        f'python {os.path.join(TOOLS_DIR, "01_anchor_collector.py")}'))

    # Step 2: Evaluate baseline
    results.append(run_step('Baseline Evaluation',
        f'python {os.path.join(SCRIPTS_DIR, "evaluate_precision.py")}'))

    # Step 3: IPv6 provider mapping (Phase 1)
    if not args.quick:
        results.append(run_step('IPv6 Provider Mapping',
            f'python {os.path.join(TOOLS_DIR, "02_ipv6_provider_mapper.py")}'))

    # Step 4: IDC locator (Phase 1)
    if not args.quick:
        results.append(run_step('IDC Locator',
            f'python {os.path.join(TOOLS_DIR, "03_idc_locator.py")}'))

    # Step 5: DB-IP extraction (Phase 2)
    results.append(run_step('DB-IP China Extraction',
        f'python {os.path.join(TOOLS_DIR, "05_dbip_china_extractor.py")}'))

    # Step 6: Vote fusion (Phase 2/4)
    results.append(run_step('Vote Fusion Engine',
        f'python {os.path.join(TOOLS_DIR, "07_vote_fusion_engine.py")}'))

    # Step 7: Build high-precision MMDB (Phase 4)
    results.append(run_step('Confidence Modeler',
        f'python {os.path.join(TOOLS_DIR, "09_confidence_modeler.py")}'))

    # Step 8: Evaluate new database
    results.append(run_step('High-Precision Evaluation',
        f'python {os.path.join(SCRIPTS_DIR, "evaluate_precision.py")} '
        f'--mmdb {os.path.join(OUTPUT_DIR, "china_ipv4_high_prec.mmdb")}'))

    # Summary
    print('\n' + '=' * 60)
    print('Pipeline Summary')
    print('=' * 60)
    passed = sum(1 for r in results if r['status'] == 'ok')
    failed = sum(1 for r in results if r['status'] != 'ok')
    print(f'  Steps: {passed} passed, {failed} failed out of {len(results)}')
    for r in results:
        status_mark = '✓' if r['status'] == 'ok' else '✗'
        print(f'  {status_mark} {r["step"]}: {r["status"]}')

    report = {
        'pipeline_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'steps': results,
        'summary': {'passed': passed, 'failed': failed, 'total': len(results)},
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\nReport: {REPORT_PATH}')


if __name__ == '__main__':
    main()
