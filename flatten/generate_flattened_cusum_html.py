#!/usr/bin/env python3

import sqlite3
import numpy as np
import random
import argparse
from tqdm import tqdm
import os
import struct
from scipy import stats

def bytes_to_float(value):
    """Convert bytes to float if needed, otherwise return as-is"""
    if isinstance(value, bytes):
        return struct.unpack('d', value)[0]
    return value

def compute_negative_cusum(y_vals, k=0.0):
    """Compute negative CUSUM with adjustable k parameter - matches original algorithm"""
    cusum = [0]
    for i in range(1, len(y_vals)):
        diff = y_vals[i] - y_vals[i - 1]
        s = min(0, cusum[-1] + (diff - k))
        cusum.append(s)
    return cusum

def smooth_curve(y_vals, window_size=5):
    """Apply smoothing to curve data"""
    if len(y_vals) < window_size:
        return y_vals
    
    smoothed = []
    half_window = window_size // 2
    
    for i in range(len(y_vals)):
        start = max(0, i - half_window)
        end = min(len(y_vals), i + half_window + 1)
        smoothed.append(sum(y_vals[start:end]) / (end - start))
    
    return smoothed

def apply_corrected_cusum_algorithm(readings, k=0.0):
    """Apply the corrected CUSUM algorithm with adjustable k parameter"""
    margin = 50
    plot_width = 800 - 2 * margin
    plot_height = 400 - 2 * margin
    
    min_reading = min(readings)
    max_reading = max(readings)
    reading_range = max_reading - min_reading if max_reading != min_reading else 1
    
    # Convert to SVG coordinates (same as original algorithm)
    svg_y_vals = []
    for reading in readings:
        svg_y = margin + plot_height - (plot_height * (reading - min_reading) / reading_range)
        svg_y_vals.append(svg_y)
    
    svg_y_vals = np.array(svg_y_vals)
    
    # Apply simple inversion
    y_inv = np.max(svg_y_vals) - svg_y_vals
    
    # Smooth the inverted data
    y_smooth = smooth_curve(y_inv)
    
    # Apply CUSUM with custom k parameter
    cusum = compute_negative_cusum(y_smooth, k=k)
    
    return cusum, min(cusum)

def get_readings_for_id(conn, target_id):
    """Get readings for a specific ID"""
    cursor = conn.cursor()
    readings_columns = [f"readings{i}" for i in range(44)]
    readings_select = ", ".join(readings_columns)
    cursor.execute(f"SELECT {readings_select} FROM readings WHERE id = ?", (target_id,))
    row = cursor.fetchone()
    if not row:
        return []
    readings = [r for r in row if r is not None]
    return readings

def find_cusum_minimum_index(cusum_values):
    """Find the index where CUSUM reaches its minimum value"""
    min_val = min(cusum_values)
    return cusum_values.index(min_val)

def create_flattened_readings(original_readings, cusum_values, cusum_min, threshold=-80, sanity_check=False, sanity_lob=False):
    """Create flattened readings for curves with significant downward trends"""
    
    # Only flatten if CUSUM min <= threshold
    if cusum_min > threshold:
        return None
    
    # Find the index where CUSUM reaches minimum (end of downward slope)
    min_index = find_cusum_minimum_index(cusum_values)
    
    # Skip if minimum occurs too early (nothing to flatten)
    if min_index <= 1:
        return None
    
    # Get the target reading value (at the minimum CUSUM point)
    target_reading = original_readings[min_index]
    
    # Sanity check: ensure the CUSUM min point actually represents a decrease
    sanity_check_passed = True
    lob_gradient = None
    
    if sanity_check:
        # Original sanity check: compare with average of early cycles
        if min_index < 5:
            # For first five cycles, compare with average of first two
            avg_first = np.mean(original_readings[:2])
        else:
            # Otherwise, compare with average of first five cycles
            avg_first = np.mean(original_readings[:5])
        
        # Check if the reading at cusum min is lower than the early average
        if target_reading >= avg_first:
            sanity_check_passed = False
            return None, min_index, sanity_check_passed, lob_gradient
    
    if sanity_lob:
        # Line of Best Fit sanity check: check gradient from first to CUSUM min
        # Use readings from index 0 to min_index (inclusive)
        x_values = np.arange(min_index + 1)
        y_values = original_readings[:min_index + 1]
        
        # Calculate line of best fit using scipy.stats.linregress
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)
        lob_gradient = slope
        
        # Check if gradient is negative (downward trend)
        if lob_gradient >= 0:
            sanity_check_passed = False
            return None, min_index, sanity_check_passed, lob_gradient
    
    # Determine appropriate noise scale based on data
    reading_std = np.std(original_readings)
    noise_scale = reading_std * 0.001  # Very small noise, 0.1% of standard deviation
    
    # Create flattened readings
    flattened = original_readings.copy()
    
    # Flatten all readings before the minimum point
    for i in range(min_index):
        # Add small random noise to prevent identical values
        noise = random.uniform(-noise_scale, noise_scale)
        flattened[i] = target_reading + noise
    
    return flattened, min_index, sanity_check_passed, lob_gradient

def generate_svg_graph_with_flattening(record_id, readings, cusum_values, cusum_min, threshold=-80, k_param=0.0, width=240, height=180, sanity_check=False, inspection_mode=False, sanity_lob=False):
    """Generate SVG graph with original, CUSUM, and flattened readings"""
    
    margin = 25
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    # Calculate LOB gradient if requested (for display purposes)
    lob_gradient = None
    if sanity_lob:
        # Find the index where CUSUM reaches minimum
        min_index = find_cusum_minimum_index(cusum_values)
        if min_index > 1:
            # Calculate line of best fit from first reading to CUSUM min
            x_values = np.arange(min_index + 1)
            y_values = readings[:min_index + 1]
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)
            lob_gradient = slope
    
    # Always evaluate sanity check if enabled (even if below threshold)
    # This lets us show sanity status regardless of threshold
    sanity_passed_check = None  # Track if sanity would pass
    below_threshold = cusum_min > threshold

    # For inspection mode, don't actually flatten - just check if we would
    would_flatten = False
    if inspection_mode:
        would_flatten = cusum_min <= threshold
        flattening_result = None
    else:
        # If sanity check enabled, ALWAYS evaluate it (even below threshold)
        if sanity_check and below_threshold:
            # Evaluate sanity without actually flattening
            min_index = find_cusum_minimum_index(cusum_values)
            target_reading = readings[min_index]
            # Calculate average of first cycles
            if min_index == 0:
                # Can't compare to earlier data - fail it
                sanity_passed_check = False
            elif min_index == 1:
                # Compare to first reading only
                sanity_passed_check = (target_reading < readings[0])
            elif min_index < 5:
                avg_first = np.mean(readings[:2])
                sanity_passed_check = (target_reading < avg_first)
            else:
                avg_first = np.mean(readings[:5])
                sanity_passed_check = (target_reading < avg_first)
            flattening_result = None  # Don't actually flatten (below threshold)
        else:
            # Normal path: try to create flattened readings
            flattening_result = create_flattened_readings(readings, cusum_values, cusum_min, threshold, sanity_check, sanity_lob)
    
    # Handle the new return format
    sanity_failed = False
    if flattening_result:
        if len(flattening_result) == 4:
            # Sanity check was performed (with LOB)
            flattened_readings, min_index, sanity_check_passed, returned_gradient = flattening_result
            # Don't override lob_gradient if we already calculated it for display
            if lob_gradient is None:
                lob_gradient = returned_gradient
            if flattened_readings is None:
                # Sanity check failed
                sanity_failed = not sanity_check_passed
                flattening_result = None
            else:
                flattening_result = (flattened_readings, min_index)
        elif len(flattening_result) == 3:
            # Old format without LOB gradient
            flattened_readings, min_index, sanity_check_passed = flattening_result
            if flattened_readings is None:
                # Sanity check failed
                sanity_failed = not sanity_check_passed
                flattening_result = None
            else:
                flattening_result = (flattened_readings, min_index)
        # else: old format, keep as is
    
    # Scale calculations
    all_values = readings.copy()
    if flattening_result and len(flattening_result) == 2:
        flattened_readings, min_index = flattening_result
        all_values.extend(flattened_readings)
    
    readings_min = min(all_values)
    readings_max = max(all_values)
    readings_range = readings_max - readings_min if readings_max != readings_min else 1
    
    cusum_min_val = min(cusum_values)
    cusum_max_val = max(cusum_values)
    cusum_range = cusum_max_val - cusum_min_val if cusum_max_val != cusum_min_val else 1
    
    max_index_plot = len(readings) - 1
    
    def x_scale(index):
        return margin + (plot_width * index / max_index_plot) if max_index_plot > 0 else margin
    
    def y_scale_readings(value):
        return margin + plot_height - ((value - readings_min) / readings_range) * plot_height
    
    def y_scale_cusum(value):
        return margin + plot_height - ((value - cusum_min_val) / cusum_range) * plot_height
    
    # Generate paths
    readings_path = []
    cusum_path = []
    flattened_path = []
    
    for i, (reading, cusum_val) in enumerate(zip(readings, cusum_values)):
        x = x_scale(i)
        y_read = y_scale_readings(reading)
        y_cusum = y_scale_cusum(cusum_val)
        
        readings_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_read:.1f}")
        cusum_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_cusum:.1f}")
    
    # Generate flattened path if applicable
    if flattening_result and len(flattening_result) == 2:
        flattened_readings, min_idx = flattening_result
        for i, flat_reading in enumerate(flattened_readings):
            x = x_scale(i)
            y_flat = y_scale_readings(flat_reading)
            flattened_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_flat:.1f}")
    
    readings_path_str = " ".join(readings_path)
    cusum_path_str = " ".join(cusum_path)
    flattened_path_str = " ".join(flattened_path) if flattened_path else ""
    
    # Status indicator
    if sanity_failed:
        if sanity_lob:
            status = "LOB SANITY FAILED"
        else:
            status = "SANITY CHECK FAILED"
        status_color = "#e74c3c"
    elif inspection_mode and would_flatten:
        status = "WOULD FLATTEN"
        status_color = "#f39c12"
    elif flattening_result:
        status = "FLATTENED"
        status_color = "#e67e22"
    elif below_threshold and sanity_passed_check is not None:
        # Below threshold but we evaluated sanity - show the result
        if sanity_passed_check:
            status = "BELOW THRESHOLD (would pass sanity)"
            status_color = "#3498db"  # Blue for informational
        else:
            status = "BELOW THRESHOLD (would fail sanity)"
            status_color = "#95a5a6"  # Gray
    else:
        status = "NO CHANGE"
        status_color = "#95a5a6"
    
    # Generate SVG
    gradient_text = f" | Gradient: {lob_gradient:.4f}" if lob_gradient is not None else ""
    svg = f'''
    <div class="graph-container">
        <div class="graph-header">
            ID {record_id} | CUSUM: {cusum_min:.1f} | k={k_param}{gradient_text}
            <span style="color: {status_color}; font-size: 10px;"> [{status}]</span>
        </div>
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <!-- Background -->
            <rect width="{width}" height="{height}" fill="white" stroke="#ccc" stroke-width="1"/>
            
            <!-- Plot area -->
            <rect x="{margin}" y="{margin}" width="{plot_width}" height="{plot_height}" 
                  fill="#f8f8f8" stroke="#ddd" stroke-width="1"/>
            
            <!-- Original readings (blue) -->
            <path d="{readings_path_str}" fill="none" stroke="blue" stroke-width="1.5" opacity="0.8"/>
            
            <!-- Flattened readings (green) - if applicable -->'''
    
    if flattened_path_str:
        svg += f'''
            <path d="{flattened_path_str}" fill="none" stroke="green" stroke-width="1.8" opacity="0.9"/>'''
    
    svg += f'''
            <!-- CUSUM (red dashed) -->
            <path d="{cusum_path_str}" fill="none" stroke="red" stroke-width="1.5" 
                  stroke-dasharray="3,2" opacity="0.9"/>
            
            <!-- Y-axis labels -->
            <text x="{margin-3}" y="{margin+5}" text-anchor="end" font-size="7" fill="blue">
                {readings_max:.2f}
            </text>
            <text x="{margin-3}" y="{margin+plot_height}" text-anchor="end" font-size="7" fill="blue">
                {readings_min:.2f}
            </text>
            
            <text x="{margin+plot_width+3}" y="{margin+5}" text-anchor="start" font-size="7" fill="red">
                {cusum_max_val:.0f}
            </text>
            <text x="{margin+plot_width+3}" y="{margin+plot_height}" text-anchor="start" font-size="7" fill="red">
                {cusum_min_val:.0f}
            </text>'''
    
    # Add flattening point marker if applicable
    if flattening_result and len(flattening_result) == 2:
        _, min_idx = flattening_result
        marker_x = x_scale(min_idx)
        marker_y = y_scale_readings(readings[min_idx])
        svg += f'''
            <!-- Flattening point marker -->
            <circle cx="{marker_x}" cy="{marker_y}" r="2" fill="orange" opacity="0.8"/>'''
    
    svg += '''
        </svg>
    </div>'''
    
    return svg

def get_example_ids(conn, sort_order='down'):
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
    if sort_order == 'none':
        # No sorting - just return in whatever order
        cursor.execute("""
        SELECT e.id, r.cusum_min_correct
        FROM example_ids e
        JOIN readings r ON e.id = r.id
        WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
        """)
    else:
        # Sort by database CUSUM values
        order_sql = "DESC" if sort_order == 'down' else "ASC"
        cursor.execute(f"""
        SELECT e.id, r.cusum_min_correct
        FROM example_ids e
        JOIN readings r ON e.id = r.id
        WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
        ORDER BY r.cusum_min_correct {order_sql}
        """)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def get_example_ids_by_sort(conn, sort_by, sort_order='down'):
    """Get example IDs with flexible sorting options"""
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
    
    # Determine sort column and order
    if sort_by == 'id':
        sort_col = "e.id"
    else:  # db-cusum or none
        sort_col = "r.cusum_min_correct"
    
    order_sql = "DESC" if sort_order == 'down' else "ASC"
    
    cursor.execute(f"""
    SELECT e.id, r.cusum_min_correct
    FROM example_ids e
    JOIN readings r ON e.id = r.id
    WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
    ORDER BY {sort_col} {order_sql}
    """)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def get_all_records(conn, sort_order='down'):
    """Get all records with specified sort order"""
    cursor = conn.cursor()
    
    if sort_order == 'none':
        cursor.execute("""
        SELECT id, cusum_min_correct
        FROM readings 
        WHERE in_use = 1 AND cusum_min_correct IS NOT NULL
        """)
    else:
        order_sql = "DESC" if sort_order == 'down' else "ASC"
        cursor.execute(f"""
        SELECT id, cusum_min_correct
        FROM readings 
        WHERE in_use = 1 AND cusum_min_correct IS NOT NULL
        ORDER BY cusum_min_correct {order_sql}
        """)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def get_all_records_by_sort(conn, sort_by, sort_order='down', group_by=None, azurecls_only=False, secondary_group_by_azurecls=False):
    """Get all records with flexible sorting options"""
    cursor = conn.cursor()

    # Determine sort column and order
    if sort_by == 'id':
        sort_col = "id"
    else:  # db-cusum
        sort_col = "cusum_min_correct"

    order_sql = "DESC" if sort_order == 'down' else "ASC"

    # Add group_by column and AzureCls if specified
    select_cols = "id, cusum_min_correct"
    if group_by:
        select_cols += f", {group_by}"
    if secondary_group_by_azurecls:
        select_cols += ", AzureCls"

    # Build WHERE clause
    where_clauses = ["in_use = 1", "cusum_min_correct IS NOT NULL"]
    if azurecls_only:
        where_clauses.append("AzureCls IS NOT NULL")
    where_clause = " AND ".join(where_clauses)

    # Build ORDER BY clause
    # Priority: primary group > secondary group (AzureCls) > sort column
    if group_by and secondary_group_by_azurecls:
        order_clause = f"{group_by}, AzureCls, {sort_col} {order_sql}"
    elif group_by:
        order_clause = f"{group_by}, {sort_col} {order_sql}"
    else:
        order_clause = f"{sort_col} {order_sql}"

    cursor.execute(f"""
    SELECT {select_cols}
    FROM readings
    WHERE {where_clause}
    ORDER BY {order_clause}
    """)

    # Convert bytes to float for cusum_min_correct
    if group_by and secondary_group_by_azurecls:
        return [(id, bytes_to_float(cusum_min), group_val, azure_cls) for id, cusum_min, group_val, azure_cls in cursor.fetchall()]
    elif group_by:
        return [(id, bytes_to_float(cusum_min), group_val) for id, cusum_min, group_val in cursor.fetchall()]
    else:
        return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def get_custom_records(conn, id_list, sort_order='down'):
    """Get custom records with specified sort order"""
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(id_list))
    
    if sort_order == 'none':
        cursor.execute(f"""
        SELECT id, cusum_min_correct
        FROM readings 
        WHERE id IN ({placeholders}) AND in_use = 1 AND cusum_min_correct IS NOT NULL
        """, id_list)
    else:
        order_sql = "DESC" if sort_order == 'down' else "ASC"
        cursor.execute(f"""
        SELECT id, cusum_min_correct
        FROM readings 
        WHERE id IN ({placeholders}) AND in_use = 1 AND cusum_min_correct IS NOT NULL
        ORDER BY cusum_min_correct {order_sql}
        """, id_list)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def get_custom_records_by_sort(conn, id_list, sort_by, sort_order='down'):
    """Get custom records with flexible sorting options"""
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(id_list))
    
    # Determine sort column and order
    if sort_by == 'id':
        sort_col = "id"
    else:  # db-cusum
        sort_col = "cusum_min_correct"
    
    order_sql = "DESC" if sort_order == 'down' else "ASC"
    
    cursor.execute(f"""
    SELECT id, cusum_min_correct
    FROM readings 
    WHERE id IN ({placeholders}) AND in_use = 1 AND cusum_min_correct IS NOT NULL
    ORDER BY {sort_col} {order_sql}
    """, id_list)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def main():
    parser = argparse.ArgumentParser(description='Generate flattened CUSUM HTML visualization')
    parser.add_argument('--k', type=float, default=0.0, 
                       help='CUSUM tolerance parameter k (default: 0.0, suggested range: 0.1-0.3)')
    parser.add_argument('--default-k', type=float, default=0.0,
                       help='Alias for --k for consistency with compare_k_parameters.py')
    parser.add_argument('--ids', type=str, 
                       help='Comma-separated list of specific IDs to process')
    parser.add_argument('--example-dataset', action='store_true',
                       help='Use example dataset from feedback plots')
    parser.add_argument('--all', action='store_true',
                       help='Process all records (alternative to --ids/--example-dataset)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of curves to process')
    parser.add_argument('--threshold', type=float, default=-80,
                       help='CUSUM threshold for flattening (default: -80)')
    parser.add_argument('--cusum-limit', type=float, default=-80,
                       help='Alias for --threshold for consistency with other scripts')
    parser.add_argument('--sort-order', choices=['up', 'down'], default='down',
                       help='Sort order: "down" = high to low (-3 before -300), "up" = low to high (-300 before -3) (default: down)')
    parser.add_argument('--sort-by', choices=['cusum', 'db-cusum', 'id'], default='cusum',
                       help='Sort by: "cusum" = calculated CUSUM values, "db-cusum" = database CUSUM (fast), "id" = record ID (default: cusum)')
    parser.add_argument('--db', type=str, default="/home/azureuser/code/wssvc-flow/readings.db",
                       help='Path to database file (default: /home/azureuser/code/wssvc-flow/readings.db)')
    parser.add_argument('--output', type=str, default="output_data",
                       help='Output directory for HTML files (default: output_data)')
    parser.add_argument('--sanity-check-slope', action='store_true',
                       help='Enable sanity check to ensure CUSUM min represents actual decrease')
    parser.add_argument('--sanity-lob', action='store_true',
                       help='Enable Line of Best Fit sanity check (gradient must be negative)')
    parser.add_argument('--only-failed', choices=['threshold', 'sanity', 'sanity-lob'],
                       help='Filter records: "threshold"=not flattened, "sanity"=failed avg check, "sanity-lob"=failed LOB check')
    parser.add_argument('--group-by', choices=['MixTarget_Full'],
                       help='Group records by specified column (e.g., MixTarget_Full for mix target grouping)')
    parser.add_argument('--azurecls-only', action='store_true',
                       help='Only include records with non-null AzureCls values')

    args = parser.parse_args()
    
    # Handle aliases
    if args.default_k != 0.0 and args.k == 0.0:
        args.k = args.default_k
    
    # Use cusum-limit if specified (alias for threshold)
    if args.cusum_limit != -80 and args.threshold == -80:
        args.threshold = args.cusum_limit
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    db_path = args.db
    
    # Generate filename based on parameters
    k_str = f"k{args.k}".replace('.', 'p')
    if args.example_dataset:
        output_file = os.path.join(args.output, f"example_cusum_{k_str}.html")
    elif args.ids:
        output_file = os.path.join(args.output, f"custom_ids_cusum_{k_str}.html")
    else:
        output_file = os.path.join(args.output, f"all_cusum_{k_str}.html")
    
    conn = sqlite3.connect(db_path)
    
    # Determine which records to process
    if args.sort_by == 'cusum' and args.k != 0.0:
        # For k!=0.0 with CUSUM sorting, get records without sorting, calculate new CUSUM, then sort
        if args.example_dataset:
            print("Using example dataset from feedback plots...")
            records = get_example_ids(conn, 'none')  # No sorting initially
            file_type = "Example Dataset"
        elif args.ids:
            print(f"Processing specific IDs: {args.ids}")
            id_list = [int(x.strip()) for x in args.ids.split(',')]
            records = get_custom_records(conn, id_list, 'none')  # No sorting initially
            file_type = "Custom IDs"
        else:
            print("Processing all records...")
            records = get_all_records(conn, 'none')  # No sorting initially
            file_type = "All Records"
        
        # Calculate new CUSUM values and sort accordingly
        print(f"Recalculating CUSUM values for k={args.k}...")
        records_with_new_cusum = []
        
        for record_id, db_cusum_min in tqdm(records, desc="Calculating new CUSUM values"):
            try:
                readings = get_readings_for_id(conn, record_id)
                if len(readings) >= 10:
                    _, new_cusum_min = apply_corrected_cusum_algorithm(readings, k=args.k)
                    records_with_new_cusum.append((record_id, new_cusum_min))
            except Exception as e:
                print(f"Error processing ID {record_id}: {e}")
                continue
        
        # Sort by new CUSUM values
        reverse_order = (args.sort_order == 'down')
        records = sorted(records_with_new_cusum, key=lambda x: x[1], reverse=reverse_order)
    else:
        # For k=0.0 with CUSUM sorting, or any k with db-cusum/id sorting (fast database sorting)
        if args.example_dataset:
            print("Using example dataset from feedback plots...")
            records = get_example_ids_by_sort(conn, args.sort_by, args.sort_order)
            file_type = "Example Dataset"
        elif args.ids:
            print(f"Processing specific IDs: {args.ids}")
            id_list = [int(x.strip()) for x in args.ids.split(',')]
            records = get_custom_records_by_sort(conn, id_list, args.sort_by, args.sort_order)
            file_type = "Custom IDs"
        else:
            print("Processing all records...")
            # Enable secondary grouping by AzureCls when using azurecls-only
            secondary_group = args.azurecls_only and args.group_by
            records = get_all_records_by_sort(conn, args.sort_by, args.sort_order, args.group_by,
                                             args.azurecls_only, secondary_group)
            file_type = "All Records"
    
    # Apply limit if specified
    if args.limit:
        records = records[:args.limit]
        print(f"Limited to {args.limit} records")
    
    print(f"Processing {len(records)} records with k={args.k}, threshold={args.threshold}, sort-by={args.sort_by}, sort-order={args.sort_order}, sanity-check={args.sanity_check_slope}, sanity-lob={args.sanity_lob}, only-failed={args.only_failed}, azurecls-only={args.azurecls_only}")

    # Generate HTML file with custom parameters
    secondary_group = args.azurecls_only and args.group_by
    generate_html_file(conn, records, output_file, file_type, args.k, args.threshold, args.sort_order, args.sort_by, args.sanity_check_slope, args.only_failed, args.sanity_lob, args.group_by, secondary_group)
    
    conn.close()

def generate_html_file(conn, records, output_file, file_type, k_param=0.0, threshold=-80, sort_order='down', sort_by='cusum', sanity_check=False, only_failed=None, sanity_lob=False, group_by=None, secondary_group_by_azurecls=False):
    """Generate HTML file with flattening visualization"""
    
    # Determine sort description
    sort_by_desc = {
        'cusum': 'Calculated CUSUM',
        'db-cusum': 'Database CUSUM',
        'id': 'Record ID'
    }
    
    if sort_order == 'down':
        order_desc = "High to Low (-3 before -300)" if sort_by != 'id' else "High to Low"
    else:
        order_desc = "Low to High (-300 before -3)" if sort_by != 'id' else "Low to High"
    
    sort_desc = f"{sort_by_desc[sort_by]} ({order_desc})"
    
    # Start HTML
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{file_type} CUSUM Graphs with Flattening - Sorted {sort_desc}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
            }}
            .container {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 8px;
                max-width: 1400px;
                margin: 0 auto;
            }}
            .graph-container {{
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
                text-align: center;
            }}
            .graph-header {{
                font-size: 11px;
                font-weight: bold;
                margin-bottom: 4px;
                color: #333;
            }}
            .header {{
                text-align: center;
                margin: 20px 0;
            }}
            .stats {{
                background: white;
                padding: 15px;
                border-radius: 4px;
                margin-bottom: 20px;
                text-align: center;
            }}
            .legend {{
                background: white;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 20px;
                text-align: center;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{file_type} CUSUM Graphs with Curve Flattening (Sorted {sort_desc})</h1>
            <div class="stats">
                <strong>Records:</strong> {len(records)}<br>
                <strong>CUSUM k parameter:</strong> {k_param}<br>
                <strong>Flattening threshold:</strong> CUSUM min ≤ {threshold}<br>
                <strong>Sanity check:</strong> {"Enabled - verifying actual decrease" if sanity_check else ("Enabled - Line of Best Fit gradient check" if sanity_lob else "Disabled")}<br>
                <strong>Method:</strong> Flatten readings before minimum CUSUM point to the target reading value
            </div>
            <div class="legend">
                <strong>Legend:</strong> 
                <span style="color: blue;">■ Blue = Original Readings</span> | 
                <span style="color: green;">■ Green = Flattened Readings</span> | 
                <span style="color: red;">■ Red Dashed = CUSUM</span> | 
                <span style="color: orange;">● Orange Dot = Flattening Point</span>''' + ('''<br>
                <span style="color: #e74c3c;">■ Red Status = Sanity Check Failed (no actual decrease)</span>''' if sanity_check else ('''<br>
                <span style="color: #e74c3c;">■ Red Status = LOB Sanity Failed (gradient >= 0)</span>''' if sanity_lob else '')) + '''
            </div>
        </div>
        <div class="container">
    '''
    
    flattened_count = 0
    sanity_failed_count = 0
    lob_failed_count = 0
    filtered_graphs = []  # Store graphs to display after filtering

    # Track current group for grouped output
    current_group = None
    group_by_col = group_by

    # Process all records but filter based on only_failed
    for i, record_tuple in enumerate(tqdm(records, desc=f"Processing {file_type.lower()} records")):
        # Unpack record based on whether we have grouping
        if group_by_col and secondary_group_by_azurecls:
            record_id, db_cusum_min, group_val, azure_cls = record_tuple
        elif group_by_col:
            record_id, db_cusum_min, group_val = record_tuple
            azure_cls = None
        else:
            record_id, db_cusum_min = record_tuple
            group_val = None
            azure_cls = None
        try:
            # Get readings
            readings = get_readings_for_id(conn, record_id)
            
            if len(readings) < 10:
                continue
            
            if k_param == 0.0:
                # Use original database CUSUM values (k=0.0 default behavior)
                cusum_columns = [f"cusum{j}" for j in range(len(readings))]
                cusum_select = ", ".join(cusum_columns)
                cursor = conn.cursor()
                cursor.execute(f"SELECT {cusum_select} FROM readings WHERE id = ?", (record_id,))
                cusum_row = cursor.fetchone()
                # Handle both float and bytes data types
                cusum_values = []
                for val in cusum_row[:len(readings)]:
                    if val is None:
                        break
                    else:
                        cusum_values.append(bytes_to_float(val))
                cusum_min = bytes_to_float(db_cusum_min)
            else:
                # Calculate CUSUM with custom k parameter
                cusum_values, cusum_min = apply_corrected_cusum_algorithm(readings, k=k_param)
            
            # For --only-failed threshold, show curves that FAILED to meet threshold (NOT flattened)
            if only_failed == 'threshold':
                # Generate WITHOUT flattening to see original curves that DON'T meet threshold
                svg_graph = generate_svg_graph_with_flattening(record_id, readings, cusum_values, 
                                                              cusum_min, threshold, k_param, 
                                                              240, 180, False, False)  # No sanity check, no inspection mode
                # Check if this record FAILED the threshold (NOT flattened)
                failed_threshold = cusum_min > threshold
                should_include = failed_threshold
                # These are NOT flattened, don't count them
            else:
                # Normal generation with flattening/sanity check
                svg_graph = generate_svg_graph_with_flattening(record_id, readings, cusum_values, 
                                                              cusum_min, threshold, k_param, 
                                                              240, 180, sanity_check, False, sanity_lob)
                
                # Check if graph shows flattened or sanity check failed
                is_sanity_failed = "SANITY CHECK FAILED" in svg_graph or "LOB SANITY FAILED" in svg_graph
                is_flattened = "FLATTENED" in svg_graph and not is_sanity_failed
                
                if is_sanity_failed:
                    if sanity_lob:
                        lob_failed_count += 1
                    else:
                        sanity_failed_count += 1
                elif is_flattened:
                    flattened_count += 1
                
                # Apply filtering based on only_failed parameter
                should_include = True
                if only_failed == 'sanity':
                    # Only include records that failed sanity check
                    should_include = is_sanity_failed
                elif only_failed == 'sanity-lob':
                    # Only include records that failed LOB sanity check
                    should_include = is_sanity_failed
                # If only_failed is None, include all
            
            if should_include:
                # Store graph with group info for later grouping
                if secondary_group_by_azurecls:
                    filtered_graphs.append((group_val, azure_cls, svg_graph))
                else:
                    filtered_graphs.append((group_val, svg_graph))
            
        except Exception as e:
            print(f"Error processing ID {record_id}: {e}")
            continue
    
    # Add filtered graphs to HTML with group headers if needed
    current_html_primary_group = None
    current_html_secondary_group = None

    # AzureCls classification labels
    azurecls_labels = {
        0: "Class 0 - Negative/Unaffected",
        1: "Class 1 - Affected/Issue Detected",
        2: "Class 2 - Severely Affected"
    }

    for graph_tuple in filtered_graphs:
        if group_by_col and secondary_group_by_azurecls:
            primary_group_val, secondary_group_val, svg_graph = graph_tuple
            # Add primary group header when primary group changes
            if primary_group_val != current_html_primary_group:
                html_content += f'''
            <h2 style="grid-column: 1 / -1; text-align: center; margin: 40px 0 10px 0; padding: 20px; background: #2c3e50; color: white; border-radius: 8px; font-size: 1.5em;">
                {group_by_col}: {primary_group_val if primary_group_val else "Unknown"}
            </h2>
'''
                current_html_primary_group = primary_group_val
                current_html_secondary_group = None  # Reset secondary group

            # Add secondary group header when secondary group changes
            if secondary_group_val != current_html_secondary_group:
                cls_label = azurecls_labels.get(secondary_group_val, f"Class {secondary_group_val}")
                html_content += f'''
            <h3 style="grid-column: 1 / -1; text-align: center; margin: 20px 0 15px 0; padding: 12px; background: #34495e; color: white; border-radius: 6px; font-size: 1.2em;">
                {cls_label}
            </h3>
'''
                current_html_secondary_group = secondary_group_val
        elif group_by_col:
            group_val, svg_graph = graph_tuple
            # Add group header when group changes
            if group_val != current_html_primary_group:
                # Add header that spans all columns in the grid
                html_content += f'''
            <h2 style="grid-column: 1 / -1; text-align: center; margin: 30px 0 20px 0; padding: 15px; background: #34495e; color: white; border-radius: 8px;">
                {group_by_col}: {group_val if group_val else "Unknown"}
            </h2>
'''
                current_html_primary_group = group_val
        else:
            # No grouping, just svg_graph
            if isinstance(graph_tuple, tuple):
                _, svg_graph = graph_tuple
            else:
                svg_graph = graph_tuple

        html_content += svg_graph
    
    # Close HTML
    filter_desc = ""
    if only_failed == 'threshold':
        filter_desc = f" (Showing only records with CUSUM > {threshold} - NOT flattened)"
    elif only_failed == 'sanity':
        filter_desc = " (Showing only sanity check failures - would flatten but failed avg comparison)"
    elif only_failed == 'sanity-lob':
        filter_desc = " (Showing only LOB sanity check failures - would flatten but gradient >= 0)"
    
    html_content += f'''
        </div>
        <div style="text-align: center; margin: 20px; color: #666;">
            <p>{file_type} dataset: {len(records)} total processed, {len(filtered_graphs)} shown{filter_desc}, {flattened_count} curves flattened''' + (f''', {sanity_failed_count} sanity check failures''' if sanity_check else (f''', {lob_failed_count} LOB sanity failures''' if sanity_lob else '')) + f''' (CUSUM ≤ {threshold})</p>
            <p>Green lines show potential flattened curves for significant downward trends</p>''' + ('''
            <p style="color: #e74c3c;">Records marked as "SANITY CHECK FAILED" have CUSUM min points that don't represent actual decreases</p>''' if sanity_check and sanity_failed_count > 0 else ('''
            <p style="color: #e74c3c;">Records marked as "LOB SANITY FAILED" have non-negative gradient from first reading to CUSUM min</p>''' if sanity_lob and lob_failed_count > 0 else '')) + '''
        </div>
    </body>
    </html>
    '''
    
    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"{file_type} HTML file generated: {output_file}")
    print(f"Graphs with flattening applied: {flattened_count}/{len(records)}")
    if sanity_check:
        print(f"Sanity check failures: {sanity_failed_count}/{len(records)}")
    if sanity_lob:
        print(f"LOB sanity failures: {lob_failed_count}/{len(records)}")

if __name__ == "__main__":
    main()