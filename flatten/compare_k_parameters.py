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

def compute_derivative(readings):
    """Compute derivative (rate of change) between consecutive readings"""
    if len(readings) < 2:
        return []
    
    derivatives = []
    for i in range(1, len(readings)):
        derivative = readings[i] - readings[i-1]
        derivatives.append(derivative)
    
    return derivatives

def find_derivative_minimum(readings):
    """Find the minimum derivative value and its index"""
    derivatives = compute_derivative(readings)
    if not derivatives:
        return 0, 0
    
    min_derivative = min(derivatives)
    # Add 1 to index because derivative array is 1 element shorter
    min_index = derivatives.index(min_derivative) + 1
    
    return min_derivative, min_index

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
    cursor.execute(f"SELECT {readings_select} FROM all_readings WHERE id = ?", (target_id,))
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
    if sanity_check:
        # Check if min_index is in first five cycles
        if min_index < 5:
            # For first five cycles, compare with average of first two
            avg_first = np.mean(original_readings[:2])
        else:
            # Otherwise, compare with average of first five cycles
            avg_first = np.mean(original_readings[:5])
        
        # Skip if the reading at cusum min is not lower than the early average
        if target_reading >= avg_first:
            return None  # Sanity check failed, don't flatten
    
    if sanity_lob:
        # Line of Best Fit sanity check: check gradient from first to CUSUM min
        # Use readings from index 0 to min_index (inclusive)
        x_values = np.arange(min_index + 1)
        y_values = original_readings[:min_index + 1]
        
        # Calculate line of best fit using scipy.stats.linregress
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)
        
        # Check if gradient is negative (downward trend)
        if slope >= 0:
            return None  # LOB sanity check failed, don't flatten
    
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
    
    return flattened, min_index

def generate_svg_comparison_graph(record_id, readings, default_values, test_values,
                                 default_min, test_min, args, threshold, 
                                 width=320, height=240):
    """Generate SVG graph comparing two methods (CUSUM or derivative) with full visualization"""
    
    margin = 30
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    # Determine flattening status for both methods
    if args.use_default_derivative:
        default_flattened = default_min <= args.derivative_threshold
    else:
        default_flattened = default_min <= threshold
    
    if args.use_test_derivative:
        test_flattened = test_min <= args.derivative_threshold
    else:
        test_flattened = test_min <= threshold
    
    # Create flattened readings if test method produces flattening
    flattening_result = None
    if test_flattened and not args.use_test_derivative:
        # Only create flattened readings for CUSUM-based test (not derivative)
        flattening_result = create_flattened_readings(readings, test_values, test_min, threshold, 
                                                      sanity_check=args.sanity_check_slope,
                                                      sanity_lob=args.sanity_lob)
    
    # Scale calculations for readings
    all_values = readings.copy()
    if flattening_result:
        flattened_readings, min_index = flattening_result
        all_values.extend(flattened_readings)
    
    readings_min = min(all_values)
    readings_max = max(all_values)
    readings_range = readings_max - readings_min if readings_max != readings_min else 1
    
    # Scale calculations for analysis values (CUSUM or derivative)
    all_analysis_values = list(default_values) + list(test_values)
    analysis_min_val = min(all_analysis_values)
    analysis_max_val = max(all_analysis_values)
    analysis_range = analysis_max_val - analysis_min_val if analysis_max_val != analysis_min_val else 1
    
    max_index_plot = len(readings) - 1
    
    def x_scale(index):
        return margin + (plot_width * index / max_index_plot) if max_index_plot > 0 else margin
    
    def y_scale_readings(value):
        return margin + plot_height - ((value - readings_min) / readings_range) * plot_height
    
    def y_scale_analysis(value):
        return margin + plot_height - ((value - analysis_min_val) / analysis_range) * plot_height
    
    # Generate readings path
    readings_path = []
    for i, reading in enumerate(readings):
        x = x_scale(i)
        y_read = y_scale_readings(reading)
        readings_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_read:.1f}")
    
    readings_path_str = " ".join(readings_path)
    
    # Generate analysis paths (CUSUM or derivative)
    default_analysis_path = []
    test_analysis_path = []
    for i, (default_val, test_val) in enumerate(zip(default_values, test_values)):
        x = x_scale(i)
        y_default = y_scale_analysis(default_val)
        y_test = y_scale_analysis(test_val)
        
        default_analysis_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_default:.1f}")
        test_analysis_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_test:.1f}")
    
    default_analysis_path_str = " ".join(default_analysis_path)
    test_analysis_path_str = " ".join(test_analysis_path)
    
    # Generate flattened path if applicable
    flattened_path_str = ""
    if flattening_result:
        flattened_readings, min_idx = flattening_result
        flattened_path = []
        for i, flat_reading in enumerate(flattened_readings):
            x = x_scale(i)
            y_flat = y_scale_readings(flat_reading)
            flattened_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_flat:.1f}")
        flattened_path_str = " ".join(flattened_path)
    
    # Determine status and color
    if default_flattened != test_flattened:
        if default_flattened and not test_flattened:
            status = f"DEFAULT FLATTENED → TEST NOT FLATTENED"
            status_color = "#e74c3c"  # Red for losing flattening
        else:
            status = f"DEFAULT NOT FLATTENED → TEST FLATTENED"
            status_color = "#27ae60"  # Green for gaining flattening
    else:
        status = "NO CHANGE IN FLATTENING"
        status_color = "#95a5a6"  # Gray for no change
    
    # Generate SVG
    svg = f'''
    <div class="graph-container">
        <div class="graph-header">
            ID {record_id} | {"Deriv" if args.use_default_derivative else f"k={args.default_k}"}: {default_min:.3f} | {"Deriv" if args.use_test_derivative else f"k={args.test_k}"}: {test_min:.3f}
        </div>
        <div class="status-indicator" style="color: {status_color}; font-size: 10px; font-weight: bold;">
            {status}
        </div>
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <!-- Background -->
            <rect width="{width}" height="{height}" fill="white" stroke="#ccc" stroke-width="1"/>
            
            <!-- Plot area -->
            <rect x="{margin}" y="{margin}" width="{plot_width}" height="{plot_height}" 
                  fill="#f8f8f8" stroke="#ddd" stroke-width="1"/>
            
            <!-- Original readings (blue) -->
            <path d="{readings_path_str}" fill="none" stroke="blue" stroke-width="1.5" opacity="0.8"/>
            '''
    
    # Add flattened readings if applicable
    if flattened_path_str:
        svg += f'''
            <!-- Flattened readings (green) -->
            <path d="{flattened_path_str}" fill="none" stroke="green" stroke-width="1.8" opacity="0.9"/>'''
    
    svg += f'''
            <!-- Default analysis (red dashed) -->
            <path d="{default_analysis_path_str}" fill="none" stroke="red" stroke-width="1.5" 
                  stroke-dasharray="3,2" opacity="0.9"/>
            
            <!-- Test analysis (orange dashed) -->
            <path d="{test_analysis_path_str}" fill="none" stroke="orange" stroke-width="1.5" 
                  stroke-dasharray="5,3" opacity="0.9"/>
            
            <!-- Y-axis labels -->
            <text x="{margin-3}" y="{margin+5}" text-anchor="end" font-size="7" fill="blue">
                {readings_max:.2f}
            </text>
            <text x="{margin-3}" y="{margin+plot_height}" text-anchor="end" font-size="7" fill="blue">
                {readings_min:.2f}
            </text>
            
            <text x="{margin+plot_width+3}" y="{margin+5}" text-anchor="start" font-size="7" fill="red">
                {analysis_max_val:.2f}
            </text>
            <text x="{margin+plot_width+3}" y="{margin+plot_height}" text-anchor="start" font-size="7" fill="red">
                {analysis_min_val:.2f}
            </text>'''
    
    # Add analysis minimum markers
    # Default method minimum marker
    default_min_idx = default_values.index(default_min) if default_min in default_values else 0
    default_marker_x = x_scale(default_min_idx)
    default_marker_y = y_scale_readings(readings[default_min_idx])
    
    svg += f'''
            <!-- Default method minimum marker -->
            <circle cx="{default_marker_x}" cy="{default_marker_y}" r="2" fill="red" opacity="0.8"/>'''
    
    # Test method minimum marker
    test_min_idx = test_values.index(test_min) if test_min in test_values else 0
    test_marker_x = x_scale(test_min_idx)
    test_marker_y = y_scale_readings(readings[test_min_idx])
    
    svg += f'''
            <!-- Test method minimum marker -->
            <circle cx="{test_marker_x}" cy="{test_marker_y}" r="2" fill="orange" opacity="0.8"/>'''
    
    # Add flattening point marker if applicable
    if flattening_result:
        _, min_idx = flattening_result
        flatten_marker_x = x_scale(min_idx)
        flatten_marker_y = y_scale_readings(readings[min_idx])
        svg += f'''
            <!-- Flattening point marker -->
            <circle cx="{flatten_marker_x}" cy="{flatten_marker_y}" r="2" fill="lime" opacity="0.9"/>'''
    
    svg += '''
        </svg>
    </div>'''
    
    return svg

def get_all_records(conn, mixes_filter=None):
    """Get all records for comparison"""
    cursor = conn.cursor()

    query = """
    SELECT id, cusum_min_correct
    FROM all_readings
    WHERE in_use = 1 AND cusum_min_correct IS NOT NULL
    """

    params = []
    if mixes_filter:
        placeholders = ','.join(['?'] * len(mixes_filter))
        query += f" AND Mix IN ({placeholders})"
        params.extend(mixes_filter)

    query += " ORDER BY cusum_min_correct ASC"

    cursor.execute(query, params)
    return cursor.fetchall()

def get_example_ids(conn, mixes_filter=None):
    """Get example IDs from database"""
    cursor = conn.cursor()

    query = """
    SELECT e.id, r.cusum_min_correct
    FROM example_ids e
    JOIN all_readings r ON e.id = r.id
    WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
    """

    params = []
    if mixes_filter:
        placeholders = ','.join(['?'] * len(mixes_filter))
        query += f" AND r.Mix IN ({placeholders})"
        params.extend(mixes_filter)

    query += " ORDER BY r.cusum_min_correct ASC"

    cursor.execute(query, params)
    return cursor.fetchall()

def main():
    parser = argparse.ArgumentParser(description='Compare CUSUM behavior between different k parameters or derivative-based analysis')
    parser.add_argument('--default-k', type=float, default=0.0, 
                       help='Default CUSUM tolerance parameter k (default: 0.0)')
    parser.add_argument('--test-k', type=float,
                       help='Test CUSUM tolerance parameter k to compare against default')
    parser.add_argument('--use-default-derivative', action='store_true',
                       help='Use derivative (rate of change) instead of CUSUM for default comparison')
    parser.add_argument('--use-test-derivative', action='store_true',
                       help='Use derivative (rate of change) instead of CUSUM for test comparison')
    parser.add_argument('--derivative-threshold', type=float,
                       help='Threshold for derivative-based flattening decision (e.g., -0.5 for drops > 0.5)')
    parser.add_argument('--cusum-limit', type=float, default=-80,
                       help='CUSUM threshold for flattening (default: -80)')
    parser.add_argument('--k', type=float,
                       help='Alias for --test-k for consistency with other scripts')
    parser.add_argument('--ids', type=str, 
                       help='Comma-separated list of specific IDs to process')
    parser.add_argument('--example-dataset', action='store_true',
                       help='Use example dataset from feedback plots')
    parser.add_argument('--all', action='store_true',
                       help='Process all records (alternative to --ids/--example-dataset)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of curves to process')
    parser.add_argument('--db', type=str, default="~/dbs/readings.db",
                       help='Path to database file (default: ~/dbs/readings.db)')
    parser.add_argument('--output', type=str, default="output_data",
                       help='Output directory for HTML files (default: output_data)')
    parser.add_argument('--threshold', type=float, default=-80,
                       help='CUSUM threshold for flattening (default: -80)')
    parser.add_argument('--sort-order', choices=['up', 'down'], default='down',
                       help='Sort order: "down" = high to low, "up" = low to high (default: down)')
    parser.add_argument('--sort-by', choices=['cusum', 'id'], default='id',
                       help='Sort by: "cusum" = CUSUM values, "id" = record ID (default: id)')
    parser.add_argument('--sanity-check-slope', action='store_true',
                       help='Enable sanity check to ensure CUSUM min represents actual decrease')
    parser.add_argument('--sanity-lob', action='store_true',
                       help='Use Line of Best Fit gradient check instead of average comparison')
    parser.add_argument('--only-failed', choices=['threshold', 'sanity', 'sanity-lob', 'changes'],
                       help='Filter results: "threshold" = would flatten, "sanity" = sanity failures, "sanity-lob" = LOB sanity failures, "changes" = flattening decision changes (default behavior)')
    parser.add_argument('--mixes', type=str,
                       help='Comma-separated list of mix names to include (default: all mixes)')

    args = parser.parse_args()

    # Parse mixes filter
    mixes_filter = None
    if args.mixes:
        mixes_filter = [mix.strip().upper() for mix in args.mixes.split(',')]
        print(f"Filtering to mixes: {', '.join(mixes_filter)}")
    
    # Handle alias --k for --test-k
    if args.k is not None:
        args.test_k = args.k
    
    # Ensure test_k is provided (unless using derivative mode for test)
    if args.test_k is None and not args.use_test_derivative:
        parser.error("--test-k (or --k) is required when not using --use-test-derivative")
    
    # Set derivative threshold if using derivative mode
    if (args.use_default_derivative or args.use_test_derivative) and args.derivative_threshold is None:
        # Default derivative threshold (negative value means downward slope)
        args.derivative_threshold = -0.1
        print(f"Using default derivative threshold: {args.derivative_threshold}")
    
    # Use threshold if specified (overrides cusum-limit)
    cusum_threshold = args.threshold if args.threshold != -80 else args.cusum_limit
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    db_path = args.db
    
    # Generate filename based on parameters
    if args.use_default_derivative:
        default_str = "deriv"
    else:
        default_str = f"k{args.default_k}".replace('.', 'p')
    
    if args.use_test_derivative:
        test_str = "deriv"
    else:
        test_str = f"k{args.test_k}".replace('.', 'p')
    
    # Use appropriate threshold in filename
    if args.use_default_derivative or args.use_test_derivative:
        limit_str = f"dlim{abs(args.derivative_threshold)}".replace('.', 'p')
    else:
        limit_str = f"lim{abs(cusum_threshold)}".replace('.', 'p')
    
    if args.example_dataset:
        output_file = os.path.join(args.output, f"comparison_example_{default_str}_vs_{test_str}_{limit_str}.html")
    elif args.ids:
        output_file = os.path.join(args.output, f"comparison_custom_{default_str}_vs_{test_str}_{limit_str}.html")
    else:
        output_file = os.path.join(args.output, f"comparison_all_{default_str}_vs_{test_str}_{limit_str}.html")
    
    conn = sqlite3.connect(db_path)
    
    # Determine which records to process
    if args.example_dataset:
        print("Using example dataset from feedback plots...")
        records = get_example_ids(conn, mixes_filter)
        file_type = "Example Dataset"
    elif args.ids:
        print(f"Processing specific IDs: {args.ids}")
        id_list = [int(x.strip()) for x in args.ids.split(',')]
        cursor = conn.cursor()

        query = """
        SELECT id, cusum_min_correct
        FROM all_readings
        WHERE id IN ({id_placeholders}) AND in_use = 1 AND cusum_min_correct IS NOT NULL
        """

        params = id_list.copy()
        id_placeholders = ','.join(['?'] * len(id_list))

        if mixes_filter:
            mix_placeholders = ','.join(['?'] * len(mixes_filter))
            query += f" AND Mix IN ({mix_placeholders})"
            params.extend(mixes_filter)

        query += " ORDER BY cusum_min_correct ASC"
        query = query.format(id_placeholders=id_placeholders)

        cursor.execute(query, params)
        records = cursor.fetchall()
        file_type = "Custom IDs"
    else:
        print("Processing all records...")
        records = get_all_records(conn, mixes_filter)
        file_type = "All Records"
    
    # Apply sorting if needed
    if args.sort_by == 'id':
        records.sort(key=lambda x: x[0], reverse=(args.sort_order == 'down'))
    elif args.sort_by == 'cusum':
        records.sort(key=lambda x: x[1], reverse=(args.sort_order == 'down'))
    
    # Apply limit if specified
    if args.limit:
        records = records[:args.limit]
        print(f"Limited to {args.limit} records")
    
    # Print processing info
    default_desc = "derivative" if args.use_default_derivative else f"k={args.default_k}"
    test_desc = "derivative" if args.use_test_derivative else f"k={args.test_k}"
    threshold_desc = f"derivative threshold={args.derivative_threshold}" if (args.use_default_derivative or args.use_test_derivative) else f"CUSUM threshold={cusum_threshold}"
    print(f"Processing {len(records)} records with default {default_desc}, test {test_desc}, {threshold_desc}")
    
    # Process records and find ones where flattening decision changes
    changing_records = []
    
    for record_id, db_cusum_min in tqdm(records, desc="Finding records with flattening changes"):
        try:
            # Get readings
            readings = get_readings_for_id(conn, record_id)
            
            if len(readings) < 10:
                continue
            
            # Calculate values for default comparison
            if args.use_default_derivative:
                # Use derivative for default
                default_min, default_min_index = find_derivative_minimum(readings)
                default_values = compute_derivative(readings)
                # Pad derivative values to match readings length for visualization
                default_values = [0] + default_values  # Add 0 at start since derivative is 1 shorter
            elif args.default_k == 0.0:
                # Use database values for default k=0.0
                default_min = bytes_to_float(db_cusum_min)
                # Get database CUSUM values
                cursor = conn.cursor()
                cusum_columns = [f"cusum{j}" for j in range(len(readings))]
                cusum_select = ", ".join(cusum_columns)
                cursor.execute(f"SELECT {cusum_select} FROM all_readings WHERE id = ?", (record_id,))
                cusum_row = cursor.fetchone()
                default_values = [bytes_to_float(val) for val in cusum_row if val is not None][:len(readings)]
            else:
                # Calculate CUSUM with default k parameter
                default_values, default_min = apply_corrected_cusum_algorithm(readings, k=args.default_k)
            
            # Calculate values for test comparison
            if args.use_test_derivative:
                # Use derivative for test
                test_min, test_min_index = find_derivative_minimum(readings)
                test_values = compute_derivative(readings)
                # Pad derivative values to match readings length for visualization
                test_values = [0] + test_values  # Add 0 at start since derivative is 1 shorter
            else:
                # Calculate CUSUM with test k parameter
                test_values, test_min = apply_corrected_cusum_algorithm(readings, k=args.test_k)
            
            # Check if flattening decision changes
            if args.use_default_derivative:
                default_flattened = default_min <= args.derivative_threshold
            else:
                default_flattened = default_min <= cusum_threshold
            
            if args.use_test_derivative:
                test_flattened = test_min <= args.derivative_threshold
            else:
                test_flattened = test_min <= cusum_threshold
            
            if default_flattened != test_flattened:
                changing_records.append((record_id, readings, default_values, test_values, 
                                       default_min, test_min))
                
        except Exception as e:
            print(f"Error processing ID {record_id}: {e}")
            continue
    
    print(f"Found {len(changing_records)} records where flattening decision changes")
    
    # Generate HTML file
    generate_html_file(changing_records, output_file, file_type, args, cusum_threshold)
    
    conn.close()

def generate_html_file(changing_records, output_file, file_type, args, threshold):
    """Generate HTML file with comparison visualization (CUSUM or derivative)"""
    
    # Determine what we're comparing
    default_desc = "Derivative" if args.use_default_derivative else f"CUSUM k={args.default_k}"
    test_desc = "Derivative" if args.use_test_derivative else f"CUSUM k={args.test_k}"
    
    # Start HTML
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Comparison: {default_desc} vs {test_desc} - {file_type}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
            }}
            .container {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 10px;
                max-width: 1600px;
                margin: 0 auto;
            }}
            .graph-container {{
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px;
                text-align: center;
            }}
            .graph-header {{
                font-size: 11px;
                font-weight: bold;
                margin-bottom: 4px;
                color: #333;
            }}
            .status-indicator {{
                margin-bottom: 6px;
                padding: 2px;
                border-radius: 2px;
                font-size: 10px;
                font-weight: bold;
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
            <h1>Comparison: {default_desc} vs {test_desc}</h1>
            <h2>{file_type}</h2>
            <div class="stats">
                <strong>Records with flattening changes:</strong> {len(changing_records)}<br>
                <strong>Default method:</strong> {default_desc}<br>
                <strong>Test method:</strong> {test_desc}<br>
                <strong>Threshold:</strong> {"Derivative min ≤ " + str(args.derivative_threshold) if (args.use_default_derivative or args.use_test_derivative) else "CUSUM min ≤ " + str(threshold)}<br>
                <strong>Showing:</strong> Only curves where flattening decision changes between methods
            </div>
            <div class="legend">
                <strong>Curves:</strong> 
                <span style="color: blue;">■ Blue = Original Readings</span> | 
                <span style="color: green;">■ Green = Flattened Readings (if test method causes flattening)</span><br>
                <strong>Analysis:</strong>
                <span style="color: red;">■ Red Dashed = {default_desc}</span> | 
                <span style="color: orange;">■ Orange Dashed = {test_desc}</span><br>
                <strong>Markers:</strong>
                <span style="color: red;">● Red = {default_desc} Min</span> | 
                <span style="color: orange;">● Orange = {test_desc} Min</span> | 
                <span style="color: lime;">● Lime = Flattening Point</span><br>
                <strong>Status:</strong>
                <span style="color: #e74c3c;">■ Red = Lost Flattening</span> | 
                <span style="color: #27ae60;">■ Green = Gained Flattening</span>
            </div>
        </div>
        <div class="container">
    '''
    
    # Generate graphs for changing records
    for record_id, readings, default_values, test_values, default_min, test_min in changing_records:
        try:
            svg_graph = generate_svg_comparison_graph(
                record_id, readings, default_values, test_values,
                default_min, test_min, args, threshold
            )
            html_content += svg_graph
            
        except Exception as e:
            print(f"Error generating graph for ID {record_id}: {e}")
            continue
    
    # Close HTML
    html_content += f'''
        </div>
        <div style="text-align: center; margin: 20px; color: #666;">
            <p>K Comparison: {len(changing_records)} curves where flattening decision changes</p>
            <p>{default_desc} vs {test_desc} with threshold ≤ {args.derivative_threshold if (args.use_default_derivative or args.use_test_derivative) else threshold}</p>
        </div>
    </body>
    </html>
    '''
    
    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"K comparison HTML file generated: {output_file}")
    print(f"Records with flattening changes: {len(changing_records)}")

if __name__ == "__main__":
    main()