#!/usr/bin/env python3

import sqlite3
import json
import uuid
from datetime import datetime
import os
import argparse
from collections import defaultdict

def generate_pcrai_from_db(db_path, filename, output_dir="output_data", table="flatten"):
    """
    Generate a PCRAI file from database records for a specific filename
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Generating PCRAI for file: {filename}")
    
    # Check if file exists in database
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE File = ?", (filename,))
    record_count = cursor.fetchone()[0]
    if record_count == 0:
        print(f"No records found for file: {filename}")
        return None
    
    print(f"Found {record_count} records for {filename}")
    
    # Generate top-level metadata
    metadata = generate_metadata(cursor, filename, table)
    
    # Generate mixes array dynamically
    mixes = generate_mixes_array(cursor, filename, table)
    
    # Generate wells array dynamically
    wells = generate_wells_array(cursor, filename, mixes, table)
    
    # Generate data array with flattened readings
    data = generate_data_array(cursor, filename, wells, table)
    
    # Create complete PCRAI structure
    pcrai = {
        "uid": metadata["uid"],
        "name": metadata["name"],
        "extension": metadata["extension"],
        "parser": metadata["parser"],
        "creation_date": metadata["creation_date"],
        "plate_size": metadata["plate_size"],
        "sample_count": metadata["sample_count"],
        "cycle_count": metadata["cycle_count"],
        "steps": {},
        "mixes": mixes,
        "wells": wells,
        "data": data
    }
    
    # Write to output file
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{filename}.pcrai")
    
    with open(output_file, 'w') as f:
        json.dump(pcrai, f, separators=(',', ':'))
    
    print(f"PCRAI file generated: {output_file}")
    print(f"Wells: {len(wells)}, Mixes: {len(mixes)}, Data shape: {len(data)}x{len(data[0])}x{len(data[0][0])}")
    
    conn.close()
    return output_file

def generate_metadata(cursor, filename, table="flatten"):
    """Generate top-level metadata for PCRAI file"""
    
    # Get unique tubes to determine plate dimensions
    cursor.execute(f"SELECT DISTINCT Tube FROM {table} WHERE File = ?", (filename,))
    tubes = [row[0] for row in cursor.fetchall()]
    
    # Parse plate dimensions from tube locations
    max_row = 'A'
    max_col = 1
    for tube in tubes:
        if len(tube) >= 2:
            row = tube[0]
            col = int(tube[1:])
            if row > max_row:
                max_row = row
            if col > max_col:
                max_col = col
    
    # Convert row letter to number for plate size
    row_num = ord(max_row) - ord('A') + 1
    plate_size = f"{row_num} X {max_col}"
    
    # Count total wells
    sample_count = len(tubes)
    
    # Get cycle count (should be 45: Results + readings0-43)
    cursor.execute(f"SELECT name FROM pragma_table_info('{table}') WHERE name LIKE 'readings%'")
    reading_columns = cursor.fetchall()
    cycle_count = len(reading_columns) + 1  # +1 for Results column
    
    return {
        "uid": str(uuid.uuid4()).replace('-', ''),
        "name": filename,
        "extension": "ixo",
        "parser": "Roche IXO",
        "creation_date": int(datetime.now().timestamp() * 1000),  # milliseconds
        "plate_size": plate_size,
        "sample_count": sample_count,
        "cycle_count": cycle_count
    }

def generate_mixes_array(cursor, filename, table="flatten"):
    """Generate mixes array dynamically from database"""
    
    # Get all unique mixes
    cursor.execute(f"SELECT DISTINCT Mix FROM {table} WHERE File = ? ORDER BY Mix", (filename,))
    mix_names = [row[0] for row in cursor.fetchall()]
    
    mixes = []
    for i, mix_name in enumerate(mix_names):
        # Get all targets and detectors for this mix (use MixTarget for improved names)
        cursor.execute(f"""
            SELECT DISTINCT MixTarget, Detector 
            FROM {table} 
            WHERE File = ? AND Mix = ? 
            ORDER BY MixTarget
        """, (filename, mix_name))
        
        targets = cursor.fetchall()
        
        # Create channels array for this mix
        channels = []
        for target, detector in targets:
            channels.append({
                "target": target,
                "detector": detector,
                "quencher": ""
            })
        
        mix_obj = {
            "id": i,
            "channels": channels,
            "group": mix_name
        }
        mixes.append(mix_obj)
    
    print(f"Generated {len(mixes)} mixes: {[m['group'] for m in mixes]}")
    return mixes

def generate_wells_array(cursor, filename, mixes, table="flatten"):
    """Generate wells array dynamically from database tubes"""
    
    # Get all unique tubes
    cursor.execute(f"SELECT DISTINCT Tube FROM {table} WHERE File = ? ORDER BY Tube", (filename,))
    tubes = [row[0] for row in cursor.fetchall()]
    
    # Create mix name to ID mapping
    mix_name_to_id = {mix["group"]: mix["id"] for mix in mixes}
    
    wells = []
    for well_id, tube in enumerate(tubes):
        # Get the mix and sample for this tube
        cursor.execute(f"""
            SELECT DISTINCT Mix, Sample 
            FROM {table} 
            WHERE File = ? AND Tube = ?
            LIMIT 1
        """, (filename, tube))
        
        result = cursor.fetchone()
        if not result:
            continue
            
        mix_name, sample_name = result
        mix_id = mix_name_to_id[mix_name]
        
        # Get all channels for this tube/mix combination (use MixTarget for improved names)
        cursor.execute(f"""
            SELECT MixTarget, Detector, Results, 
                   readings0, readings1, readings2, readings3, readings4, readings5,
                   readings6, readings7, readings8, readings9, readings10, readings11,
                   readings12, readings13, readings14, readings15, readings16, readings17,
                   readings18, readings19, readings20, readings21, readings22, readings23,
                   readings24, readings25, readings26, readings27, readings28, readings29,
                   readings30, readings31, readings32, readings33, readings34, readings35,
                   readings36, readings37, readings38, readings39, readings40, readings41,
                   readings42, readings43
            FROM {table} 
            WHERE File = ? AND Tube = ? AND Mix = ?
            ORDER BY MixTarget
        """, (filename, tube, mix_name))
        
        channel_records = cursor.fetchall()
        
        # Create channels array for this well
        channels = []
        for record in channel_records:
            target = record[0]
            detector = record[1]
            
            # Get all readings (Results + readings0-43)
            readings = [r for r in record[2:] if r is not None]
            
            # Calculate basic result metrics (simplified for now)
            max_reading = max(readings) if readings else 0
            
            channel = {
                "volume": 0,
                "type": "Unknown",
                "embedded": {
                    "result": {
                        "Cq": 0,  # Could calculate from readings if needed
                        "Ci": 0,
                        "RFU": max_reading,
                        "Cls": 1 if max_reading > 1 else 0,
                        "DF": -1 if max_reading > 1 else 1
                    }
                }
            }
            channels.append(channel)
        
        well = {
            "id": well_id,
            "name": sample_name,
            "location": tube,
            "mix": mix_id,
            "channels": channels
        }
        wells.append(well)
    
    print(f"Generated {len(wells)} wells")
    return wells

def generate_data_array(cursor, filename, wells, table="flatten"):
    """Generate data array with flattened readings from database"""
    
    data = []
    
    for well in wells:
        tube = well["location"]
        well_mix_id = well["mix"]
        
        # Get mix name from well's mix ID
        cursor.execute(f"""
            SELECT DISTINCT Mix 
            FROM {table} 
            WHERE File = ? AND Tube = ?
            LIMIT 1
        """, (filename, tube))
        
        mix_name = cursor.fetchone()[0]
        
        # Get all channel data for this tube/mix (use MixTarget for improved names)
        cursor.execute(f"""
            SELECT MixTarget, Results, 
                   readings0, readings1, readings2, readings3, readings4, readings5,
                   readings6, readings7, readings8, readings9, readings10, readings11,
                   readings12, readings13, readings14, readings15, readings16, readings17,
                   readings18, readings19, readings20, readings21, readings22, readings23,
                   readings24, readings25, readings26, readings27, readings28, readings29,
                   readings30, readings31, readings32, readings33, readings34, readings35,
                   readings36, readings37, readings38, readings39, readings40, readings41,
                   readings42, readings43
            FROM {table} 
            WHERE File = ? AND Tube = ? AND Mix = ?
            ORDER BY MixTarget
        """, (filename, tube, mix_name))
        
        channel_records = cursor.fetchall()
        
        well_data = []
        for record in channel_records:
            # Get all readings (Results + readings0-43) and filter out None values
            readings = [r for r in record[1:] if r is not None]
            well_data.append(readings)
        
        data.append(well_data)
    
    print(f"Generated data array: {len(data)} wells x variable channels x 45 cycles")
    return data

def get_all_filenames(db_path, table="flatten"):
    """Get all unique filenames from the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT DISTINCT File FROM {table} ORDER BY File")
    filenames = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return filenames

def validate_pcrai_file(filepath, filename):
    """Validate a generated PCRAI file and show basic stats"""
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return False
    
    try:
        file_size = os.path.getsize(filepath)
        print(f"  File size: {file_size:,} bytes")
        
        # Load and validate basic structure
        with open(filepath, 'r') as f:
            pcrai_data = json.load(f)
        
        print(f"  Top-level keys: {list(pcrai_data.keys())}")
        print(f"  Mixes: {len(pcrai_data['mixes'])} - {[m['group'] for m in pcrai_data['mixes']]}")
        print(f"  Wells: {len(pcrai_data['wells'])}")
        print(f"  Data shape: {len(pcrai_data['data'])} x {len(pcrai_data['data'][0])} x {len(pcrai_data['data'][0][0])}")
        return True
        
    except Exception as e:
        print(f"ERROR validating {filepath}: {e}")
        return False

def main():
    """Generate PCRAI files based on command line arguments"""
    parser = argparse.ArgumentParser(description='Generate PCRAI files from database')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', 
                      help='Generate PCRAI for all unique filenames in database')
    group.add_argument('--files', type=str,
                      help='Generate PCRAI for specific files (comma-separated)')
    parser.add_argument('--db', type=str, default="/home/azureuser/code/wssvc-flow/readings.db",
                       help='Path to database file')
    parser.add_argument('--output', type=str, default="output_data",
                       help='Output directory for PCRAI files')
    parser.add_argument('--table', type=str, default='flatten',
                       help='Source table to read from (default: flatten)')
    
    args = parser.parse_args()
    
    db_path = args.db
    output_dir = args.output
    
    # Determine which files to process
    if args.all:
        print("Getting all unique filenames from database...")
        filenames = get_all_filenames(db_path, args.table)
        print(f"Found {len(filenames)} unique files: {filenames}")
    else:
        filenames = [f.strip() for f in args.files.split(',')]
        print(f"Processing specified files: {filenames}")
    
    # Generate PCRAI files
    successful_files = []
    failed_files = []
    
    for filename in filenames:
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
        print('='*60)
        
        try:
            output_file = generate_pcrai_from_db(db_path, filename, output_dir, args.table)
            if output_file:
                print(f"✓ PCRAI generated: {output_file}")
                
                # Validate the generated file
                print("Validating generated file:")
                if validate_pcrai_file(output_file, filename):
                    successful_files.append(filename)
                else:
                    failed_files.append(filename)
            else:
                print(f"✗ Failed to generate PCRAI for: {filename}")
                failed_files.append(filename)
                
        except Exception as e:
            print(f"✗ Error processing {filename}: {e}")
            failed_files.append(filename)
    
    # Summary
    print(f"\n{'='*60}")
    print("GENERATION SUMMARY")
    print('='*60)
    print(f"Total files processed: {len(filenames)}")
    print(f"Successful: {len(successful_files)}")
    print(f"Failed: {len(failed_files)}")
    
    if successful_files:
        print(f"\nSuccessful files: {successful_files}")
    
    if failed_files:
        print(f"\nFailed files: {failed_files}")

if __name__ == "__main__":
    main()