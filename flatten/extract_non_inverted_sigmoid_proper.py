#!/usr/bin/env python3
"""
Extract Parvo and HHV6 results that don't have inverted sigmoid curves.
Creates PCRAI files in the proper format for import.
"""

import sqlite3
import json
import argparse
import os
from datetime import datetime
from collections import defaultdict
import hashlib
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.database import bytes_to_float

def is_inverted_sigmoid(readings):
    """
    Check if readings show an inverted (downward) sigmoid pattern.
    Based on PHP SigmoidIdentifier logic: inverted if middle > penultimate
    
    Returns True if inverted sigmoid (should be excluded)
    Returns False if not inverted (should be included)
    Returns None if insufficient data
    """
    # Filter out None values and convert bytes if needed
    valid_readings = []
    for r in readings:
        if r is not None:
            if isinstance(r, bytes):
                valid_readings.append(bytes_to_float(r))
            else:
                valid_readings.append(float(r))
    
    # Need more than 3 valid readings
    if len(valid_readings) <= 3:
        return None
    
    # Calculate middle index (matching PHP ArrayItemsSeeker logic)
    count = len(valid_readings)
    if count % 2 == 0:
        middle_index = (count // 2) - 1
    else:
        middle_index = round(count / 2) - 1
    
    # Penultimate index is actually last index in the PHP code
    penultimate_index = count - 1
    
    middle_value = valid_readings[middle_index]
    penultimate_value = valid_readings[penultimate_index]
    
    # Inverted sigmoid: middle > penultimate
    return middle_value > penultimate_value

def get_run_structure(quest_conn, run_id):
    """
    Get the complete structure of a run including mixes, wells, and observations.
    """
    cursor = quest_conn.cursor()
    
    # Get run info
    cursor.execute("""
        SELECT run_name, created_at 
        FROM runs 
        WHERE id = ?
    """, (run_id,))
    run_info = cursor.fetchone()
    if not run_info:
        return None
    
    # Get all mixes used in this run (based on targets in observations)
    cursor.execute("""
        SELECT DISTINCT 
            m.id as mix_id,
            m.mix_name,
            t.target_name,
            d.dye_name as detector,
            d.quencher
        FROM wells w
        JOIN observations o ON w.id = o.well_id
        JOIN targets t ON o.target_id = t.id
        JOIN mixes m ON t.mix_id = m.id
        LEFT JOIN dyes d ON t.dye_id = d.id
        WHERE w.run_id = ?
        AND t.target_name NOT LIKE '%REFERENCE%'
        AND (
            UPPER(t.target_name) LIKE '%PARVO%'
            OR UPPER(t.target_name) LIKE '%HHV6%'
            OR UPPER(t.target_name) LIKE '%HHV-6%'
            OR UPPER(t.target_name) LIKE '%IPC%'
            OR UPPER(t.target_name) LIKE '%IC%'
        )
        ORDER BY m.mix_name, t.target_name
    """, (run_id,))
    
    mix_targets = cursor.fetchall()
    
    # Group targets by mix
    mixes_dict = {}
    for mix_id, mix_name, target_name, detector, quencher in mix_targets:
        if mix_name not in mixes_dict:
            mixes_dict[mix_name] = {
                'id': len(mixes_dict),
                'channels': [],
                'group': mix_name
            }
        mixes_dict[mix_name]['channels'].append({
            'target': target_name,
            'detector': detector or '',
            'quencher': quencher or ''
        })
    
    # Get wells with Parvo/HHV6 observations (patient samples only)
    cursor.execute("""
        SELECT DISTINCT
            w.id as well_id,
            w.well_number,
            w.sample_label,
            w.role_alias,
            m.mix_name
        FROM wells w
        JOIN observations o ON w.id = o.well_id
        JOIN targets t ON o.target_id = t.id
        JOIN mixes m ON t.mix_id = m.id
        WHERE w.run_id = ?
        AND (w.role_alias = 'Patient' OR w.role_alias = '' OR w.role_alias IS NULL)
        AND (
            UPPER(t.target_name) LIKE '%PARVO%'
            OR UPPER(t.target_name) LIKE '%HHV6%'
            OR UPPER(t.target_name) LIKE '%HHV-6%'
        )
        ORDER BY w.well_number
    """, (run_id,))
    
    wells_data = cursor.fetchall()
    
    wells_list = []
    data_list = []
    valid_well_count = 0
    cycle_count = None  # Track actual cycle count
    
    for well_id, well_number, sample_label, role_alias, mix_name in wells_data:
        # Skip well A11 from TAQMAN47 run
        if 'TAQMAN47 031324_022808' in run_info[0] and well_number == 'A11':
            continue
        # Get all observations for this well
        cursor.execute("""
            SELECT 
                t.target_name,
                o.machine_cls,
                o.final_cls,
                o.machine_ct,
                o.final_ct,
                o.readings
            FROM observations o
            JOIN targets t ON o.target_id = t.id
            WHERE o.well_id = ?
            AND t.target_name NOT LIKE '%REFERENCE%'
            ORDER BY t.target_name
        """, (well_id,))
        
        observations = cursor.fetchall()
        
        # Check if any Parvo/HHV6 observation has inverted sigmoid
        has_inverted_sigmoid = False
        has_valid_target = False
        
        for target_name, _, _, _, _, readings_json in observations:
            if 'PARVO' in target_name.upper() or 'HHV' in target_name.upper():
                has_valid_target = True
                try:
                    readings = json.loads(readings_json) if readings_json else []
                    if is_inverted_sigmoid(readings):
                        has_inverted_sigmoid = True
                        break
                except:
                    pass
        
        # Skip wells with inverted sigmoid Parvo/HHV6 curves
        if has_inverted_sigmoid or not has_valid_target:
            continue
        
        # Build well structure
        well_dict = {
            'id': valid_well_count,
            'name': sample_label,
            'location': well_number,
            'mix': mixes_dict.get(mix_name, {}).get('id', 0),
            'channels': []
        }
        
        # Build data arrays for this well
        well_data = []
        
        # Add channels based on mix definition
        if mix_name in mixes_dict:
            for channel_def in mixes_dict[mix_name]['channels']:
                # Find matching observation
                obs_found = False
                for target_name, machine_cls, final_cls, machine_ct, final_ct, readings_json in observations:
                    if target_name == channel_def['target']:
                        obs_found = True
                        # Parse readings
                        try:
                            readings = json.loads(readings_json) if readings_json else []
                        except:
                            readings = []
                        
                        # Keep original cycle count (no padding/truncation)
                        if readings and cycle_count is None:
                            cycle_count = len(readings)
                        
                        # Add channel data
                        well_dict['channels'].append({
                            'volume': 0,
                            'type': 'Unknown',
                            'embedded': {
                                'result': {
                                    'Cq': machine_ct or 0,
                                    'Ci': 0,
                                    'RFU': readings[-1] if readings else 0,
                                    'Cls': machine_cls if machine_cls is not None else 0,
                                    'DF': -1
                                }
                            }
                        })
                        
                        well_data.append(readings)
                        break
                
                if not obs_found:
                    # Add empty channel if target not found
                    well_dict['channels'].append({
                        'volume': 0,
                        'type': 'Unknown',
                        'embedded': {
                            'result': {
                                'Cq': 0,
                                'Ci': 0,
                                'RFU': 0,
                                'Cls': 0,
                                'DF': -1
                            }
                        }
                    })
                    well_data.append([0.0] * (cycle_count or 45))
        
        wells_list.append(well_dict)
        data_list.append(well_data)
        valid_well_count += 1
    
    # Also get control wells for the mixes we're using
    control_wells = []
    control_data = []
    
    if valid_well_count > 0:
        # Get control wells
        cursor.execute("""
            SELECT DISTINCT
                w.id as well_id,
                w.well_number,
                w.sample_label,
                w.role_alias,
                m.mix_name
            FROM wells w
            JOIN observations o ON w.id = o.well_id
            JOIN targets t ON o.target_id = t.id
            JOIN mixes m ON t.mix_id = m.id
            WHERE w.run_id = ?
            AND w.role_alias NOT IN ('Patient', '')
            AND w.role_alias IS NOT NULL
            AND m.mix_name IN ({})
            ORDER BY w.well_number
        """.format(','.join('?' * len(mixes_dict))), (run_id, *list(mixes_dict.keys())))
        
        controls_data = cursor.fetchall()
        
        for well_id, well_number, sample_label, role_alias, mix_name in controls_data:
            # Get observations for control well
            cursor.execute("""
                SELECT 
                    t.target_name,
                    o.machine_cls,
                    o.final_cls,
                    o.machine_ct,
                    o.final_ct,
                    o.readings
                FROM observations o
                JOIN targets t ON o.target_id = t.id
                WHERE o.well_id = ?
                AND t.target_name NOT LIKE '%REFERENCE%'
                ORDER BY t.target_name
            """, (well_id,))
            
            observations = cursor.fetchall()
            
            well_dict = {
                'id': valid_well_count,
                'name': f"{role_alias}: {sample_label}",
                'location': well_number,
                'mix': mixes_dict.get(mix_name, {}).get('id', 0),
                'channels': []
            }
            
            well_data = []
            
            # Add channels based on mix definition
            if mix_name in mixes_dict:
                for channel_def in mixes_dict[mix_name]['channels']:
                    obs_found = False
                    for target_name, machine_cls, final_cls, machine_ct, final_ct, readings_json in observations:
                        if target_name == channel_def['target']:
                            obs_found = True
                            try:
                                readings = json.loads(readings_json) if readings_json else []
                            except:
                                readings = []
                            
                            # Keep original cycle count (no padding/truncation)
                            
                            well_dict['channels'].append({
                                'volume': 0,
                                'type': 'Unknown',
                                'embedded': {
                                    'result': {
                                        'Cq': machine_ct or 0,
                                        'Ci': 0,
                                        'RFU': readings[-1] if readings else 0,
                                        'Cls': machine_cls if machine_cls is not None else 0,
                                        'DF': -1
                                    }
                                }
                            })
                            well_data.append(readings)
                            break
                    
                    if not obs_found:
                        well_dict['channels'].append({
                            'volume': 0,
                            'type': 'Unknown',
                            'embedded': {
                                'result': {
                                    'Cq': 0,
                                    'Ci': 0,
                                    'RFU': 0,
                                    'Cls': 0,
                                    'DF': -1
                                }
                            }
                        })
                        well_data.append([0.0] * (cycle_count or 45))
            
            control_wells.append(well_dict)
            control_data.append(well_data)
            valid_well_count += 1
    
    if valid_well_count == 0:
        return None
    
    # Determine target type for filename
    has_parvo = any('PARVO' in ch['target'].upper() for m in mixes_dict.values() for ch in m['channels'])
    has_hhv6 = any('HHV' in ch['target'].upper() for m in mixes_dict.values() for ch in m['channels'])
    
    if has_parvo and has_hhv6:
        target_type = 'hhv6-parvo'
    elif has_parvo:
        target_type = 'parvo'
    elif has_hhv6:
        target_type = 'hhv6'
    else:
        target_type = 'unknown'
    
    # Generate uid (remove non-alphanumeric from run_id)
    uid = ''.join(c for c in run_id if c.isalnum())
    
    # Build PCRAI structure
    pcrai_data = {
        'uid': uid,
        'name': run_info[0].replace('.sds', f'_{target_type}.sds') if '.sds' in run_info[0] else f"{run_info[0]}_{target_type}",
        'extension': 'sds',
        'parser': 'ABI SDS',
        'creation_date': int(datetime.fromisoformat(run_info[1]).timestamp() * 1000),
        'plate_size': '96 X 1',  # Standard 96-well plate
        'sample_count': len(wells_list) + len(control_wells),
        'cycle_count': cycle_count or 45,
        'steps': {},
        'mixes': list(mixes_dict.values()),
        'wells': wells_list + control_wells,
        'data': data_list + control_data
    }
    
    return pcrai_data, target_type

def main():
    parser = argparse.ArgumentParser(description='Extract non-inverted sigmoid Parvo/HHV6 data in proper PCRAI format')
    parser.add_argument('--db', type=str, default='input_data/quest_prod_aug2025.db',
                       help='Path to Quest production database')
    parser.add_argument('--output-dir', type=str, default='output_data/pcrai_non_inverted',
                       help='Output directory for PCRAI files')
    parser.add_argument('--report', type=str, default='output_data/non_inverted_sigmoid_report.html',
                       help='Output HTML report path')
    
    args = parser.parse_args()
    
    # Connect to database
    quest_conn = sqlite3.connect(args.db)
    cursor = quest_conn.cursor()
    
    # Create output directory if needed
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    
    print("Finding runs with Parvo/HHV6 targets...")
    
    # Get all runs with Parvo/HHV6 targets
    cursor.execute("""
        SELECT DISTINCT r.id, r.run_name
        FROM runs r
        JOIN wells w ON r.id = w.run_id
        JOIN observations o ON w.id = o.well_id
        JOIN targets t ON o.target_id = t.id
        WHERE (
            UPPER(t.target_name) LIKE '%PARVO%'
            OR UPPER(t.target_name) LIKE '%HHV6%'
            OR UPPER(t.target_name) LIKE '%HHV-6%'
        )
        AND (w.role_alias = 'Patient' OR w.role_alias = '' OR w.role_alias IS NULL)
        ORDER BY r.run_name
    """)
    
    runs = cursor.fetchall()
    print(f"Found {len(runs)} runs with Parvo/HHV6 targets")
    
    created_files = []
    skipped_runs = []
    
    for run_id, run_name in runs:
        print(f"Processing run {run_name}...")
        
        # Get run structure and filter inverted sigmoids
        result = get_run_structure(quest_conn, run_id)
        
        if result is None:
            print(f"  Skipped (all samples have inverted sigmoid)")
            skipped_runs.append((run_id, run_name))
            continue
        
        pcrai_data, target_type = result
        
        # Create filename
        safe_run_name = run_name.replace('/', '_').replace('\\', '_').replace('.sds', '')
        safe_run_id = ''.join(c for c in run_id if c.isalnum())
        filename = f"{safe_run_name}_{target_type}_{safe_run_id}.pcrai"
        filepath = os.path.join(args.output_dir, filename)
        
        # Write PCRAI file
        with open(filepath, 'w') as f:
            json.dump(pcrai_data, f, indent=2)
        
        print(f"  Created: {filename} ({pcrai_data['sample_count']} samples, {pcrai_data['cycle_count']} cycles)")
        created_files.append((filename, pcrai_data['sample_count'], target_type))
    
    quest_conn.close()
    
    # Generate summary report
    print(f"\n=== Summary ===")
    print(f"Total runs processed: {len(runs)}")
    print(f"PCRAI files created: {len(created_files)}")
    print(f"Runs skipped (inverted sigmoid): {len(skipped_runs)}")
    print(f"Output directory: {args.output_dir}")
    
    # Generate HTML report
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Non-Inverted Sigmoid PCRAI Extraction Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f0f0f0; }}
        .summary {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .skipped {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Non-Inverted Sigmoid PCRAI Extraction Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Total runs processed: {len(runs)}</p>
        <p>PCRAI files created: {len(created_files)}</p>
        <p>Runs skipped (inverted sigmoid): {len(skipped_runs)}</p>
    </div>
    
    <h2>Created Files</h2>
    <table>
        <tr><th>Filename</th><th>Samples</th><th>Target Type</th></tr>
"""
    
    for filename, sample_count, target_type in sorted(created_files):
        html += f"        <tr><td>{filename}</td><td>{sample_count}</td><td>{target_type}</td></tr>\n"
    
    html += """    </table>
    
    <h2>Skipped Runs</h2>
    <table>
        <tr><th>Run ID</th><th>Run Name</th><th>Reason</th></tr>
"""
    
    for run_id, run_name in skipped_runs:
        html += f'        <tr class="skipped"><td>{run_id}</td><td>{run_name}</td><td>All samples have inverted sigmoid</td></tr>\n'
    
    html += """    </table>
</body>
</html>
"""
    
    with open(args.report, 'w') as f:
        f.write(html)
    
    print(f"HTML report: {args.report}")

if __name__ == "__main__":
    main()