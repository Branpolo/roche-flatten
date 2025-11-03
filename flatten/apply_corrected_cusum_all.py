#!/usr/bin/env python3

import sqlite3
import numpy as np
import pandas as pd
from tqdm import tqdm
import argparse
import os

# Import from utils
try:
    from utils.database import get_readings_for_id, get_example_ids
    from utils.algorithms import compute_negative_cusum
except ModuleNotFoundError:
    from flatten.utils.database import get_readings_for_id, get_example_ids
    from flatten.utils.algorithms import compute_negative_cusum

def process_readings_with_corrected_algorithm(readings, k=0.0):
    """Apply the corrected CUSUM algorithm"""
    # Convert to SVG coordinates (as in gpt-combined approach)
    width, height = 800, 400
    margin = 50
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    min_reading = min(readings)
    max_reading = max(readings)
    reading_range = max_reading - min_reading if max_reading != min_reading else 1
    
    # Convert to SVG coordinates
    svg_y_vals = []
    for idx, reading in enumerate(readings):
        svg_y = margin + plot_height - (plot_height * (reading - min_reading) / reading_range)
        svg_y_vals.append(svg_y)
    
    svg_y_vals = np.array(svg_y_vals)
    
    # Apply simple inversion on SVG coordinates
    y_inv = np.max(svg_y_vals) - svg_y_vals
    # Use pandas rolling for smoothing to match original implementation
    y_smooth = pd.Series(y_inv).rolling(window=5, min_periods=1, center=True).mean().to_numpy()
    cusum = compute_negative_cusum(y_smooth, k=k)
    
    return cusum

# get_example_ids is now imported from utils.database

def main():
    parser = argparse.ArgumentParser(description='Apply corrected CUSUM algorithm to readings')
    parser.add_argument('--db', type=str, default="/home/azureuser/code/wssvc-flow/readings.db",
                       help='Path to database file (default: /home/azureuser/code/wssvc-flow/readings.db)')
    parser.add_argument('--output', type=str, default="output_data",
                       help='Output directory for any generated files (default: output_data)')
    parser.add_argument('--cusum-limit', type=float, default=-10,
                       help='CUSUM threshold for determining negative slope (default: -10)')
    parser.add_argument('--k', type=float, default=0.0,
                       help='CUSUM tolerance parameter k (default: 0.0)')
    parser.add_argument('--ids', type=str,
                       help='Comma-separated list of specific IDs to process')
    parser.add_argument('--example-dataset', action='store_true',
                       help='Use example dataset from feedback plots')
    parser.add_argument('--limit', type=int,
                       help='Limit number of records to process')
    parser.add_argument('--threshold', type=float, default=-10,
                       help='CUSUM threshold for determining negative slope (default: -10)')
    parser.add_argument('--sort-order', choices=['up', 'down'], default='down',
                       help='Sort order: "down" = high to low, "up" = low to high (default: down)')
    parser.add_argument('--sort-by', choices=['cusum', 'id'], default='id',
                       help='Sort by: "cusum" = CUSUM values, "id" = record ID (default: id)')
    parser.add_argument('--table', type=str, default='readings',
                       help='Table to process (default: readings)')

    args = parser.parse_args()
    
    # Use threshold if specified (overrides cusum-limit)
    cusum_threshold = args.threshold if args.threshold != -10 else args.cusum_limit
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()
    
    # Determine which IDs to process
    if args.ids:
        # Process specific IDs
        in_use_ids = [int(x.strip()) for x in args.ids.split(',')]
        print(f"Processing specific IDs: {in_use_ids}")
    elif args.example_dataset:
        # Use example dataset
        in_use_ids = get_example_ids(conn)
        print(f"Processing example dataset ({len(in_use_ids)} records)...")
    else:
        # Get all in_use records
        cursor.execute(f"SELECT id FROM {args.table} WHERE in_use = 1")
        in_use_ids = [row[0] for row in cursor.fetchall()]
        print(f"Processing all {len(in_use_ids)} in_use records from {args.table}...")
    
    # Apply sorting
    if args.sort_by == 'id':
        in_use_ids.sort(reverse=(args.sort_order == 'down'))
    
    # Apply limit if specified
    if args.limit:
        in_use_ids = in_use_ids[:args.limit]
        print(f"Limited to {args.limit} records")
    
    print(f"Using k={args.k}, threshold={cusum_threshold}")
    print(f"Database: {args.db}")
    print(f"Output directory: {args.output}")
    print(f"Sort by: {args.sort_by}, order: {args.sort_order}")
    print()
    
    # Process each record
    for record_id in tqdm(in_use_ids, desc="Processing records"):
        try:
            # Get readings
            readings = get_readings_for_id(conn, record_id, table=args.table)

            if len(readings) < 10:  # Skip if insufficient data
                print(f"Skipping ID {record_id}: insufficient data ({len(readings)} readings)")
                continue

            # Apply corrected CUSUM algorithm with k parameter
            cusum = process_readings_with_corrected_algorithm(readings, k=args.k)
            cusum_min = cusum.min()

            # Determine negative slope using specified threshold
            negative_slope = 1 if cusum_min < cusum_threshold else 0

            # Prepare CUSUM values for database (pad with None if needed)
            cusum_values = list(cusum) + [None] * (44 - len(cusum))

            # Update database with CUSUM values
            cusum_columns = [f"cusum{i}" for i in range(44)]
            cusum_placeholders = ", ".join(["?" for _ in range(44)])
            cusum_updates = ", ".join([f"{col} = ?" for col in cusum_columns])

            update_query = f"""
            UPDATE {args.table}
            SET {cusum_updates},
                cusum_min_correct = ?,
                cusum_negative_slope_correct = ?
            WHERE id = ?
            """

            cursor.execute(update_query, cusum_values + [cusum_min, negative_slope, record_id])
            
        except Exception as e:
            print(f"Error processing ID {record_id}: {e}")
            continue
    
    # Commit changes
    conn.commit()
    
    # Summary statistics for processed records only
    if in_use_ids:
        placeholders = ','.join(['?'] * len(in_use_ids))
        cursor.execute(f"""
        SELECT
            COUNT(*) as total_processed,
            COUNT(CASE WHEN cusum_negative_slope_correct = 1 THEN 1 END) as negative_slopes,
            MIN(cusum_min_correct) as min_cusum,
            MAX(cusum_min_correct) as max_cusum,
            AVG(cusum_min_correct) as avg_cusum
        FROM {args.table}
        WHERE id IN ({placeholders}) AND in_use = 1 AND cusum_min_correct IS NOT NULL
        """, in_use_ids)
        
        stats = cursor.fetchone()
        print(f"\nProcessing complete!")
        print(f"Total processed: {stats[0]}")
        print(f"Records with negative slopes: {stats[1]}")
        if stats[2] is not None and stats[3] is not None:
            try:
                min_val = float(stats[2])
                max_val = float(stats[3])
                print(f"CUSUM range: {min_val:.1f} to {max_val:.1f}")
            except (ValueError, TypeError):
                print(f"CUSUM range: Unable to convert values (may contain binary data)")
        if stats[4] is not None:
            try:
                avg_val = float(stats[4])
                print(f"Average CUSUM minimum: {avg_val:.1f}")
            except (ValueError, TypeError):
                print(f"Average CUSUM minimum: Unable to convert (may contain binary data)")
    else:
        print(f"\nProcessing complete! No records processed.")
    
    conn.close()

if __name__ == "__main__":
    main()