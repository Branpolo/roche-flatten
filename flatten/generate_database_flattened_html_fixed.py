#!/usr/bin/env python3

import sqlite3
from tqdm import tqdm
import argparse
import os

def get_readings_and_cusum_from_db(conn, table_name, record_id):
    """Get readings and CUSUM values from specified table"""
    cursor = conn.cursor()
    
    # Get flattened readings from the table (Results + readings0-43)
    readings_columns = ["Results"] + [f"readings{i}" for i in range(44)]
    readings_select = ", ".join(readings_columns)
    cursor.execute(f"SELECT {readings_select} FROM {table_name} WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    
    if not row:
        return None, None
    
    # Process readings (filter None values)
    all_readings = [r for r in row if r is not None]
    
    if len(all_readings) < 10:
        return None, None
    
    # Get CUSUM values - offset by 1 since Results column was added
    # CUSUM was calculated on readings0-43, but now we have Results + readings0-43
    # So cusum0 corresponds to readings0 (index 1 in our all_readings array)
    cusum_length = len(all_readings) - 1  # Skip the Results column for CUSUM mapping
    cusum_columns = [f"cusum{j}" for j in range(cusum_length)]
    cusum_select = ", ".join(cusum_columns)
    
    try:
        cursor.execute(f"SELECT {cusum_select} FROM {table_name} WHERE id = ?", (record_id,))
        cusum_row = cursor.fetchone()
        
        if cusum_row:
            cusum_values = [val for val in cusum_row if val is not None]
            # Add a 0 at the beginning to align with the Results column
            cusum_values = [0.0] + cusum_values
            # Ensure CUSUM length matches readings length
            cusum_values = cusum_values[:len(all_readings)]
            return all_readings, cusum_values
        else:
            return None, None
            
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            # Some records might not have all CUSUM columns, get what we can
            available_cusum = [0.0]  # Start with 0 for Results column
            for j in range(cusum_length):
                try:
                    cursor.execute(f"SELECT cusum{j} FROM {table_name} WHERE id = ?", (record_id,))
                    val = cursor.fetchone()
                    if val and val[0] is not None:
                        available_cusum.append(val[0])
                    else:
                        break
                except sqlite3.OperationalError:
                    break
            
            if len(available_cusum) >= 10:  # Need minimum data for visualization
                return all_readings[:len(available_cusum)], available_cusum
            else:
                return None, None
        else:
            raise e

def generate_svg_graph_with_db_data(record_id, flattened_readings, original_cusum, cusum_min, width=240, height=180, cusum_threshold=-80):
    """Generate SVG graph showing flattened readings (from DB) with original CUSUM overlay"""
    
    margin = 25
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    # Ensure same length for both datasets
    min_length = min(len(flattened_readings), len(original_cusum))
    flattened_readings = flattened_readings[:min_length]
    original_cusum = original_cusum[:min_length]
    
    # Scale calculations for readings
    readings_min = min(flattened_readings)
    readings_max = max(flattened_readings)
    readings_range = readings_max - readings_min if readings_max != readings_min else 1
    
    # Scale calculations for CUSUM
    cusum_min_val = min(original_cusum)
    cusum_max_val = max(original_cusum)
    cusum_range = cusum_max_val - cusum_min_val if cusum_max_val != cusum_min_val else 1
    
    max_index = len(flattened_readings) - 1
    
    def x_scale(index):
        return margin + (plot_width * index / max_index) if max_index > 0 else margin
    
    def y_scale_readings(value):
        return margin + plot_height - ((value - readings_min) / readings_range) * plot_height
    
    def y_scale_cusum(value):
        return margin + plot_height - ((value - cusum_min_val) / cusum_range) * plot_height
    
    # Generate paths
    readings_path = []
    cusum_path = []
    
    for i, (reading, cusum_val) in enumerate(zip(flattened_readings, original_cusum)):
        x = x_scale(i)
        y_read = y_scale_readings(reading)
        y_cusum = y_scale_cusum(cusum_val)
        
        readings_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_read:.1f}")
        cusum_path.append(f"{'M' if i == 0 else 'L'} {x:.1f} {y_cusum:.1f}")
    
    readings_path_str = " ".join(readings_path)
    cusum_path_str = " ".join(cusum_path)
    
    # Determine status based on threshold
    was_flattened = cusum_min <= cusum_threshold
    status = "FLATTENED" if was_flattened else "UNCHANGED"
    status_color = "#27ae60" if was_flattened else "#95a5a6"
    
    # Generate SVG
    svg = f'''
    <div class="graph-container">
        <div class="graph-header">
            ID {record_id} | CUSUM: {cusum_min:.1f}
            <span style="color: {status_color}; font-size: 10px;"> [{status}]</span>
        </div>
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <!-- Background -->
            <rect width="{width}" height="{height}" fill="white" stroke="#ccc" stroke-width="1"/>
            
            <!-- Plot area -->
            <rect x="{margin}" y="{margin}" width="{plot_width}" height="{plot_height}" 
                  fill="#f8f8f8" stroke="#ddd" stroke-width="1"/>
            
            <!-- Flattened readings from DB (green/blue based on status) -->
            <path d="{readings_path_str}" fill="none" stroke="{"#27ae60" if was_flattened else "#3498db"}" stroke-width="2" opacity="0.9"/>
            
            <!-- Original CUSUM overlay (red dashed) -->
            <path d="{cusum_path_str}" fill="none" stroke="red" stroke-width="1.5" 
                  stroke-dasharray="3,2" opacity="0.7"/>
            
            <!-- Y-axis labels -->
            <text x="{margin-3}" y="{margin+5}" text-anchor="end" font-size="7" fill="{"#27ae60" if was_flattened else "#3498db"}">
                {readings_max:.2f}
            </text>
            <text x="{margin-3}" y="{margin+plot_height}" text-anchor="end" font-size="7" fill="{"#27ae60" if was_flattened else "#3498db"}">
                {readings_min:.2f}
            </text>
            
            <text x="{margin+plot_width+3}" y="{margin+5}" text-anchor="start" font-size="7" fill="red">
                {cusum_max_val:.0f}
            </text>
            <text x="{margin+plot_width+3}" y="{margin+plot_height}" text-anchor="start" font-size="7" fill="red">
                {cusum_min_val:.0f}
            </text>
        </svg>
    </div>'''
    
    return svg

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
    
    # Get example IDs that exist in the flatten table
    cursor.execute("""
    SELECT e.id
    FROM example_ids e
    JOIN flatten r ON e.id = r.id
    WHERE r.in_use = 1
    """)
    
    return [row[0] for row in cursor.fetchall()]

def main():
    parser = argparse.ArgumentParser(description='Generate HTML visualization of database flattened curves')
    parser.add_argument('--db', type=str, default="/home/azureuser/code/wssvc-flow/readings.db",
                       help='Path to database file (default: /home/azureuser/code/wssvc-flow/readings.db)')
    parser.add_argument('--output', type=str, default="output_data",
                       help='Output directory for HTML files (default: output_data)')
    parser.add_argument('--cusum-limit', type=float, default=-80,
                       help='CUSUM threshold for determining flattening status (default: -80)')
    parser.add_argument('--ids', type=str,
                       help='Comma-separated list of specific IDs to process')
    parser.add_argument('--example-dataset', action='store_true',
                       help='Use example dataset from feedback plots')
    parser.add_argument('--limit', type=int, default=500,
                       help='Limit number of records to process (default: 500)')
    parser.add_argument('--threshold', type=float, default=-80,
                       help='CUSUM threshold for determining flattening status (default: -80)')
    parser.add_argument('--sort-order', choices=['up', 'down'], default='up',
                       help='Sort order: "down" = high to low, "up" = low to high (default: up)')
    parser.add_argument('--sort-by', choices=['cusum', 'id'], default='cusum',
                       help='Sort by: "cusum" = CUSUM values, "id" = record ID (default: cusum)')
    
    args = parser.parse_args()
    
    # Use threshold if specified (overrides cusum-limit)
    cusum_threshold = args.threshold if args.threshold != -80 else args.cusum_limit
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    # Generate output filename
    if args.example_dataset:
        output_file = os.path.join(args.output, "example_database_flattened_curves.html")
        file_type = "Example"
    elif args.ids:
        output_file = os.path.join(args.output, "custom_database_flattened_curves.html")
        file_type = "Custom"
    else:
        output_file = os.path.join(args.output, "sample_database_flattened_curves.html")
        file_type = "Sample"
    
    print(f"Database: {args.db}")
    print(f"Output directory: {args.output}")
    print(f"CUSUM threshold: {cusum_threshold}")
    print(f"Sort by: {args.sort_by}, order: {args.sort_order}")
    print(f"Limit: {args.limit}")
    
    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()
    
    # Build query based on options
    where_conditions = ["in_use = 1", "cusum_min_correct IS NOT NULL"]
    query_params = []
    
    # Handle ID selection
    if args.ids:
        # Process specific IDs
        id_list = [int(x.strip()) for x in args.ids.split(',')]
        placeholders = ','.join(['?'] * len(id_list))
        where_conditions.append(f"id IN ({placeholders})")
        query_params.extend(id_list)
        print(f"Processing specific IDs: {id_list}")
    elif args.example_dataset:
        # Use example dataset
        example_ids = get_example_ids(conn)
        placeholders = ','.join(['?'] * len(example_ids))
        where_conditions.append(f"id IN ({placeholders})")
        query_params.extend(example_ids)
        print(f"Processing example dataset ({len(example_ids)} records)...")
    
    where_clause = " AND ".join(where_conditions)
    
    # Add sorting
    if args.sort_by == 'cusum':
        order_by = f"cusum_min_correct {'DESC' if args.sort_order == 'down' else 'ASC'}"
    else:  # id
        order_by = f"id {'DESC' if args.sort_order == 'down' else 'ASC'}"
    
    # Build and execute query
    query = f"""
    SELECT id, cusum_min_correct
    FROM flatten 
    WHERE {where_clause}
    ORDER BY {order_by}
    LIMIT ?
    """
    
    query_params.append(args.limit)
    cursor.execute(query, query_params)
    
    records = cursor.fetchall()
    print(f"Processing {len(records)} records from flattened database...")
    
    generate_html_file(conn, records, output_file, file_type, cusum_threshold)
    
    conn.close()

def generate_html_file(conn, records, output_file, file_type, cusum_threshold=-80):
    """Generate HTML file showing database flattened curves with original CUSUM"""
    
    # Start HTML
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{file_type} Database Flattened Curves with Original CUSUM</title>
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
            <h1>{file_type} Database Flattened Curves</h1>
            <div class="stats">
                <strong>Records:</strong> {len(records)}<br>
                <strong>Source:</strong> Database "flatten" table with modified readings<br>
                <strong>Visualization:</strong> Shows actual flattened curves with original CUSUM overlay
            </div>
            <div class="legend">
                <strong>Legend:</strong> 
                <span style="color: #27ae60;">■ Green = Flattened Readings (from DB)</span> | 
                <span style="color: #3498db;">■ Blue = Unchanged Readings (from DB)</span> | 
                <span style="color: red;">■ Red Dashed = Original CUSUM (overlay)</span>
            </div>
        </div>
        <div class="container">
    '''
    
    flattened_count = 0
    processed_count = 0
    
    # Generate graphs
    for i, (record_id, cusum_min) in enumerate(tqdm(records, desc=f"Generating {file_type.lower()} DB graphs")):
        try:
            # Get flattened readings and original CUSUM from database
            flattened_readings, original_cusum = get_readings_and_cusum_from_db(conn, "flatten", record_id)
            
            if not flattened_readings or len(flattened_readings) < 10:
                continue
            
            # Check if this was flattened based on threshold
            if cusum_min <= cusum_threshold:
                flattened_count += 1
            
            # Generate SVG with threshold
            svg_graph = generate_svg_graph_with_db_data(record_id, flattened_readings, original_cusum, cusum_min, cusum_threshold=cusum_threshold)
            html_content += svg_graph
            processed_count += 1
            
        except Exception as e:
            print(f"Error processing ID {record_id}: {e}")
            continue
    
    # Close HTML
    html_content += f'''
        </div>
        <div style="text-align: center; margin: 20px; color: #666;">
            <p>{file_type} dataset: {processed_count} graphs from "flatten" table, {flattened_count} were flattened (CUSUM ≤ {cusum_threshold})</p>
            <p>Green curves = actually flattened in database | Red dashed = original CUSUM for comparison</p>
        </div>
    </body>
    </html>
    '''
    
    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"{file_type} HTML file generated: {output_file}")
    print(f"Graphs processed: {processed_count}, Flattened curves shown: {flattened_count}")

if __name__ == "__main__":
    main()