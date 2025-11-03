#!/usr/bin/env python3

import sqlite3
import numpy as np
import random
import argparse
from scipy import stats

def get_example_ids(conn):
    """Get example IDs from database"""
    cursor = conn.cursor()
    
    # First check if example_ids table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        print("Creating example_ids table...")
        cursor.execute("CREATE TABLE example_ids (id INTEGER PRIMARY KEY)")
        
        # Insert the example IDs from feedback plots + 2112 (key test case)
        example_ids = [3, 8, 9, 10, 20, 30, 33, 38, 49, 59, 60, 199, 203, 206, 367, 386, 
                      427, 434, 479, 486, 600, 601, 820, 1256, 1264, 1276, 1339, 1340, 
                      1782, 1825, 1862, 1877, 2112, 2300, 2304]
        
        for example_id in example_ids:
            cursor.execute("INSERT INTO example_ids (id) VALUES (?)", (example_id,))
        
        conn.commit()
        print(f"Populated example_ids table with {len(example_ids)} IDs")
    
    # Get example IDs that exist in the readings table
    cursor.execute("""
    SELECT e.id
    FROM example_ids e
    JOIN readings r ON e.id = r.id
    WHERE r.in_use = 1
    """)
    
    return [row[0] for row in cursor.fetchall()]

def main():
    parser = argparse.ArgumentParser(description='Create flattened database for CUSUM analysis')
    parser.add_argument('--db', type=str, default="/home/azureuser/code/wssvc-flow/readings.db",
                       help='Path to database file (default: /home/azureuser/code/wssvc-flow/readings.db)')
    parser.add_argument('--cusum-limit', type=float, default=-80,
                       help='CUSUM threshold for flattening (default: -80)')
    parser.add_argument('--ids', type=str,
                       help='Comma-separated list of specific IDs to process')
    parser.add_argument('--example-dataset', action='store_true',
                       help='Use example dataset from feedback plots')
    parser.add_argument('--limit', type=int,
                       help='Limit number of records to process')
    parser.add_argument('--threshold', type=float, default=-80,
                       help='CUSUM threshold for flattening (default: -80)')
    parser.add_argument('--sort-order', choices=['up', 'down'], default='down',
                       help='Sort order: "down" = high to low, "up" = low to high (default: down)')
    parser.add_argument('--sort-by', choices=['cusum', 'id'], default='cusum',
                       help='Sort by: "cusum" = CUSUM values, "id" = record ID (default: cusum)')
    parser.add_argument('--sanity-check-slope', action='store_true',
                       help='Enable sanity check to ensure CUSUM min represents actual decrease')
    parser.add_argument('--sanity-lob', action='store_true',
                       help='Use Line of Best Fit gradient check instead of average comparison')
    parser.add_argument('--source-table', type=str, default='readings',
                       help='Source table to read from (default: readings)')
    parser.add_argument('--dest-table', type=str, default='flatten',
                       help='Destination table to write to (default: flatten)')

    args = parser.parse_args()
    
    # Use threshold if specified (overrides cusum-limit)
    cusum_threshold = args.threshold if args.threshold != -80 else args.cusum_limit

    print(f"Database: {args.db}")
    print(f"Source table: {args.source_table}")
    print(f"Destination table: {args.dest_table}")
    print(f"CUSUM threshold: {cusum_threshold}")
    print(f"Sort by: {args.sort_by}, order: {args.sort_order}")

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    print(f"Creating {args.dest_table} table copy from {args.source_table}...")

    # Create the destination table as a copy of the source
    cursor.execute(f"DROP TABLE IF EXISTS {args.dest_table}")
    cursor.execute(f"CREATE TABLE {args.dest_table} AS SELECT * FROM {args.source_table}")
    
    print("Processing flattening with optimized approach...")
    
    # Build WHERE clause based on options
    where_conditions = ["in_use = 1", "cusum_min_correct IS NOT NULL", f"cusum_min_correct <= {cusum_threshold}"]
    
    # Handle ID selection
    if args.ids:
        # Process specific IDs
        id_list = [int(x.strip()) for x in args.ids.split(',')]
        placeholders = ','.join(['?'] * len(id_list))
        where_conditions.append(f"id IN ({placeholders})")
        query_params = id_list
        print(f"Processing specific IDs: {id_list}")
    elif args.example_dataset:
        # Use example dataset
        example_ids = get_example_ids(conn)
        placeholders = ','.join(['?'] * len(example_ids))
        where_conditions.append(f"id IN ({placeholders})")
        query_params = example_ids
        print(f"Processing example dataset ({len(example_ids)} records)...")
    else:
        query_params = []
        print("Processing all eligible records...")
    
    where_clause = " AND ".join(where_conditions)
    
    # Add sorting
    if args.sort_by == 'cusum':
        order_by = f"cusum_min_correct {'DESC' if args.sort_order == 'down' else 'ASC'}"
    else:  # id
        order_by = f"id {'DESC' if args.sort_order == 'down' else 'ASC'}"
    
    # Build query
    query = f"""
    SELECT id, cusum_min_correct,
           readings0, readings1, readings2, readings3, readings4, readings5, readings6, readings7, readings8, readings9,
           readings10, readings11, readings12, readings13, readings14, readings15, readings16, readings17, readings18, readings19,
           readings20, readings21, readings22, readings23, readings24, readings25, readings26, readings27, readings28, readings29,
           readings30, readings31, readings32, readings33, readings34, readings35, readings36, readings37, readings38, readings39,
           readings40, readings41, readings42, readings43,
           cusum0, cusum1, cusum2, cusum3, cusum4, cusum5, cusum6, cusum7, cusum8, cusum9,
           cusum10, cusum11, cusum12, cusum13, cusum14, cusum15, cusum16, cusum17, cusum18, cusum19,
           cusum20, cusum21, cusum22, cusum23, cusum24, cusum25, cusum26, cusum27, cusum28, cusum29,
           cusum30, cusum31, cusum32, cusum33, cusum34, cusum35, cusum36, cusum37, cusum38, cusum39,
           cusum40, cusum41, cusum42, cusum43
    FROM {args.dest_table}
    WHERE {where_clause}
    ORDER BY {order_by}
    """
    
    # Apply limit in SQL if specified
    if args.limit:
        query += f" LIMIT {args.limit}"
    
    # Execute query
    cursor.execute(query, query_params)
    
    records = cursor.fetchall()
    print(f"Found {len(records)} records that need flattening (CUSUM <= -80)...")
    
    flattened_count = 0
    sanity_failed_count = 0
    batch_updates = []
    
    for record in records:
        try:
            record_id = record[0]
            cusum_min = record[1]
            
            # Extract readings (skip None values)
            readings_raw = record[2:46]  # readings0 to readings43
            readings = [r for r in readings_raw if r is not None]
            
            if len(readings) < 10:
                continue
            
            # Extract CUSUM values (skip None values)
            cusum_raw = record[46:90]  # cusum0 to cusum43
            cusum_values = [c for c in cusum_raw if c is not None][:len(readings)]
            
            # Find CUSUM minimum index
            min_val = min(cusum_values)
            min_index = cusum_values.index(min_val)
            
            # Skip if minimum occurs too early
            if min_index <= 1:
                continue
            
            # Get target reading
            target_reading = readings[min_index]
            
            # Sanity check: ensure the CUSUM min point actually represents a decrease
            if args.sanity_check_slope:
                # Check if min_index is in first five cycles
                if min_index < 5:
                    # For first five cycles, compare with average of first two
                    avg_first = np.mean(readings[:2])
                else:
                    # Otherwise, compare with average of first five cycles
                    avg_first = np.mean(readings[:5])
                
                # Skip if the reading at cusum min is not lower than the early average
                if target_reading >= avg_first:
                    sanity_failed_count += 1
                    continue
            
            if args.sanity_lob:
                # Line of Best Fit sanity check: check gradient from first to CUSUM min
                # Use readings from index 0 to min_index (inclusive)
                x_values = np.arange(min_index + 1)
                y_values = readings[:min_index + 1]
                
                # Calculate line of best fit using scipy.stats.linregress
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)
                
                # Check if gradient is negative (downward trend)
                if slope >= 0:
                    sanity_failed_count += 1
                    continue
            reading_std = np.std(readings)
            noise_scale = reading_std * 0.001
            
            flattened_readings = readings.copy()
            
            # Flatten readings before minimum point
            for i in range(min_index):
                noise = random.uniform(-noise_scale, noise_scale)
                flattened_readings[i] = target_reading + noise
            
            # Create new Results value
            pre_flatten_reading = readings[max(0, min_index - 1)]
            results_noise = random.uniform(-noise_scale, noise_scale)
            new_results_value = pre_flatten_reading + results_noise
            
            # Pad flattened readings
            padded_readings = flattened_readings + [None] * (44 - len(flattened_readings))
            
            # Add to batch
            batch_updates.append([new_results_value] + padded_readings + [record_id])
            flattened_count += 1
            
            # Process in batches of 1000
            if len(batch_updates) >= 1000:
                print(f"Processing batch... ({flattened_count} flattened so far)")
                process_batch(cursor, batch_updates, args.dest_table)
                batch_updates = []

        except Exception as e:
            print(f"Error processing ID {record[0]}: {e}")
            continue

    # Process remaining batch
    if batch_updates:
        print(f"Processing final batch...")
        process_batch(cursor, batch_updates, args.dest_table)
    
    # Commit changes
    conn.commit()
    
    print(f"\nFlattening complete!")
    print(f"Records flattened: {flattened_count}")
    if args.sanity_check_slope:
        print(f"Sanity check failures (skipped): {sanity_failed_count}")
    if args.sanity_lob:
        print(f"LOB sanity check failures (skipped): {sanity_failed_count}")
    
    conn.close()

def process_batch(cursor, batch_updates, dest_table):
    """Process a batch of updates"""
    update_query = f"""
    UPDATE {dest_table}
    SET Results = ?, readings0 = ?, readings1 = ?, readings2 = ?, readings3 = ?, readings4 = ?, readings5 = ?, readings6 = ?, readings7 = ?, readings8 = ?, readings9 = ?,
        readings10 = ?, readings11 = ?, readings12 = ?, readings13 = ?, readings14 = ?, readings15 = ?, readings16 = ?, readings17 = ?, readings18 = ?, readings19 = ?,
        readings20 = ?, readings21 = ?, readings22 = ?, readings23 = ?, readings24 = ?, readings25 = ?, readings26 = ?, readings27 = ?, readings28 = ?, readings29 = ?,
        readings30 = ?, readings31 = ?, readings32 = ?, readings33 = ?, readings34 = ?, readings35 = ?, readings36 = ?, readings37 = ?, readings38 = ?, readings39 = ?,
        readings40 = ?, readings41 = ?, readings42 = ?, readings43 = ?
    WHERE id = ?
    """

    cursor.executemany(update_query, batch_updates)

if __name__ == "__main__":
    main()