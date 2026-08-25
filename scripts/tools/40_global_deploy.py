#!/usr/bin/env python3
"""
S10: Deployment & Documentation (Phase 10 of Global Pipeline)
Backs up old v2board files, replaces with new ones, creates rollback script.
"""
import csv, json, os, sys, io, shutil
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE, 'output')
IPDB_DIR = r'E:/v2board/resources/ipdb'
BACKUP_DIR = os.path.join(IPDB_DIR, f'backup_global_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
ROLLBACK_SCRIPT = os.path.join(IPDB_DIR, 'rollback_global.ps1')

# Mapping: new output file -> v2board target name
FILES = [
    (os.path.join(OUTPUT_DIR, 'global_ipv4_residential.mmdb'), 'global_ipv4_residential.mmdb'),
    (os.path.join(OUTPUT_DIR, 'global_ipv4_idc.mmdb'), 'global_ipv4_idc.mmdb'),
    (os.path.join(OUTPUT_DIR, 'global_ipv6_residential.mmdb'), 'global_ipv6_residential.mmdb'),
    (os.path.join(OUTPUT_DIR, 'global_ipv6_idc.mmdb'), 'global_ipv6_idc.mmdb'),
]

def main():
    print('=' * 60)
    print('S10: Deployment & Documentation')
    print('=' * 60)
    
    # Step 1: Backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'Backup directory: {BACKUP_DIR}')
    for _, target_name in FILES:
        src = os.path.join(IPDB_DIR, target_name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, target_name))
            print(f'  [BACKUP] {target_name}')
    
    # Step 2: Replace
    replaced = []
    for src_path, target_name in FILES:
        if not os.path.exists(src_path):
            print(f'  [SKIP] {src_path} not found')
            continue
        dst = os.path.join(IPDB_DIR, target_name)
        shutil.copy2(src_path, dst)
        replaced.append(target_name)
        print(f'  [REPLACE] {src_path} -> {dst} ({os.path.getsize(dst)} bytes)')
    
    # Step 3: Create rollback script
    rollback_cmds = []
    rollback_cmds.append(f'# Rollback script - generated {datetime.now()}')
    rollback_cmds.append(f'$backup = "{BACKUP_DIR}"')
    rollback_cmds.append(f'$ipdb = "{IPDB_DIR}"')
    rollback_cmds.append('')
    for _, target_name in FILES:
        rollback_cmds.append(f'if (Test-Path "$backup/{target_name}") {{')
        rollback_cmds.append(f'    Copy-Item "$backup/{target_name}" "$ipdb/{target_name}" -Force')
        rollback_cmds.append(f'    Write-Output "Restored: {target_name}"')
        rollback_cmds.append('}')
    
    with open(ROLLBACK_SCRIPT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rollback_cmds))
    print(f'  [ROLLBACK] {ROLLBACK_SCRIPT}')
    
    print(f'\nDone. Replaced {len(replaced)} files.')

if __name__ == '__main__':
    main()
