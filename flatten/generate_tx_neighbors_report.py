#!/usr/bin/env python3
"""
Generate HTML report for TX samples with nearest neighbors by CUSUM similarity.
"""

import sqlite3
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flatten.utils.database import bytes_to_float

def find_nearest_neighbors_cusum(conn, target_id, mix, mixtarget, count=10):
    """
    Find N nearest neighbors by CUSUM similarity within same mix/target.

    Returns records with closest cusum_min_correct values (higher and lower).
    """
    cursor = conn.cursor()

    # Get target record's CUSUM value
    cursor.execute("""
        SELECT cusum_min_correct FROM all_readings
        WHERE id = ? AND in_use = 1
    """, (target_id,))
    result = cursor.fetchone()
    if not result:
        return [], []

    target_cusum = bytes_to_float(result[0])
    if target_cusum is None:
        return [], []

    # Get all records for this mix/target sorted by CUSUM
    cursor.execute("""
        SELECT id, Sample, cusum_min_correct
        FROM all_readings
        WHERE Mix = ? AND MixTarget = ? AND in_use = 1
        AND cusum_min_correct IS NOT NULL
        ORDER BY cusum_min_correct DESC
    """, (mix, mixtarget))

    records = [(row[0], row[1], bytes_to_float(row[2])) for row in cursor.fetchall()]

    # Find target index
    target_index = None
    for idx, (rec_id, sample, cusum) in enumerate(records):
        if rec_id == target_id:
            target_index = idx
            break

    if target_index is None:
        return [], []

    # Get neighbors above (higher CUSUM)
    higher = []
    for idx in range(target_index - 1, -1, -1):
        higher.append(records[idx])
        if len(higher) == count:
            break

    # Get neighbors below (lower CUSUM)
    lower = []
    for idx in range(target_index + 1, len(records)):
        lower.append(records[idx])
        if len(lower) == count:
            break

    # Reverse higher for display order (highest to closest)
    higher_display = list(reversed(higher))

    return higher_display, lower

def generate_html_report(conn, record_ids_with_targets, output_file, neighbor_count=10):
    """Generate HTML report with nearest neighbors."""

    cursor = conn.cursor()

    # Build HTML header (avoid .format() conflicts with CSS braces)
    html_header = """<!DOCTYPE html>
<html>
<head>
    <title>TX Samples - Nearest Neighbors Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .sample-section {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .sample-header {{
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        .sample-title {{ color: #4CAF50; font-size: 1.4em; font-weight: bold; }}
        .sample-info {{ color: #666; margin-top: 5px; }}
        .neighbors-section {{ margin-top: 20px; }}
        .neighbor-group {{ margin: 15px 0; }}
        .neighbor-group-title {{
            font-weight: bold;
            color: #555;
            margin-bottom: 10px;
            font-size: 1.1em;
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th {{
            background: #4CAF50;
            color: white;
            padding: 10px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 8px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{ background: #f9f9f9; }}
        .target-row {{ background: #fff3cd; font-weight: bold; }}
        .higher-neighbor {{ background: #e8f5e9; }}
        .lower-neighbor {{ background: #ffebee; }}
        .cusum-value {{ font-family: monospace; }}
        .stats {{
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <h1>TX Samples - Nearest Neighbors by CUSUM Similarity</h1>
    <p><strong>Database:</strong> ~/dbs/readings.db</p>
    <p><strong>Neighbors per sample:</strong> {neighbor_count} higher CUSUM + {neighbor_count} lower CUSUM</p>
""".format(neighbor_count=neighbor_count)

    html_parts = [html_header]

    for record_id, mix, target in record_ids_with_targets:
        # Get target record info
        cursor.execute("""
            SELECT id, Sample, Mix, MixTarget, cusum_min_correct
            FROM all_readings
            WHERE id = ? AND in_use = 1
        """, (record_id,))

        row = cursor.fetchone()
        if not row:
            continue

        rec_id, sample, rec_mix, rec_target, cusum = row
        cusum_val = bytes_to_float(cusum)

        # Get nearest neighbors
        higher_neighbors, lower_neighbors = find_nearest_neighbors_cusum(
            conn, record_id, mix, target, neighbor_count
        )

        cusum_display = f"{cusum_val:.2f}" if cusum_val is not None else "N/A"

        html_parts.append(f"""
    <div class="sample-section">
        <div class="sample-header">
            <div class="sample-title">Sample {sample} - {rec_mix}:{rec_target}</div>
            <div class="sample-info">Record ID: {rec_id} | CUSUM Min: {cusum_display}</div>
        </div>

        <div class="stats">
            <strong>Neighbors found:</strong> {len(higher_neighbors)} higher, {len(lower_neighbors)} lower (within {rec_mix}:{rec_target})
        </div>

        <div class="neighbors-section">
            <div class="neighbor-group">
                <div class="neighbor-group-title">⬆️ Higher CUSUM Values (less negative = less downward trend)</div>
                <table>
                    <tr>
                        <th>Rank</th>
                        <th>ID</th>
                        <th>Sample</th>
                        <th>CUSUM Min</th>
                        <th>Difference</th>
                    </tr>
""")

        # Higher neighbors
        for idx, (n_id, n_sample, n_cusum) in enumerate(higher_neighbors, 1):
            diff = n_cusum - cusum_val if cusum_val else None
            diff_str = f"+{diff:.2f}" if diff else "N/A"
            html_parts.append(f"""
                    <tr class="higher-neighbor">
                        <td>-{len(higher_neighbors) - idx + 1}</td>
                        <td>{n_id}</td>
                        <td>{n_sample}</td>
                        <td class="cusum-value">{n_cusum:.2f}</td>
                        <td>{diff_str}</td>
                    </tr>
""")

        # Target row
        html_parts.append(f"""
                    <tr class="target-row">
                        <td><strong>TARGET</strong></td>
                        <td><strong>{rec_id}</strong></td>
                        <td><strong>{sample}</strong></td>
                        <td class="cusum-value"><strong>{cusum_display}</strong></td>
                        <td>—</td>
                    </tr>
""")

        # Lower neighbors
        for idx, (n_id, n_sample, n_cusum) in enumerate(lower_neighbors, 1):
            diff = n_cusum - cusum_val if cusum_val else None
            diff_str = f"{diff:.2f}" if diff else "N/A"
            html_parts.append(f"""
                    <tr class="lower-neighbor">
                        <td>+{idx}</td>
                        <td>{n_id}</td>
                        <td>{n_sample}</td>
                        <td class="cusum-value">{n_cusum:.2f}</td>
                        <td>{diff_str}</td>
                    </tr>
""")

        html_parts.append("""
                </table>
            </div>
        </div>
    </div>
""")

    html_parts.append("""
</body>
</html>
""")

    # Write to file
    with open(output_file, 'w') as f:
        f.write(''.join(html_parts))

    print(f"✓ Report generated: {output_file}")

def main():
    # Your specific records
    records = [
        (34316, 'TX', 'CMV'),   # Sample 1536470
        (39314, 'TX', 'EBV'),   # Sample 1536107
        (42321, 'TX', 'Adeno'), # Sample 1536068
        (40621, 'TX', 'Adeno'), # Sample 1529725
        (29780, 'TX', 'CMV'),   # Sample 1534061
        (40156, 'TX', 'CMV'),   # Sample 1530621
    ]

    db_path = os.path.expanduser('~/dbs/readings.db')
    output_file = 'output_data/tx_samples_nearest_neighbors.html'

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    try:
        generate_html_report(conn, records, output_file, neighbor_count=10)
        print(f"\n✓ Successfully generated report for {len(records)} TX samples")
        print(f"✓ Output: {output_file}")
        print(f"\nSamples included:")
        for rec_id, mix, target in records:
            cursor = conn.cursor()
            cursor.execute("SELECT Sample FROM all_readings WHERE id = ?", (rec_id,))
            sample = cursor.fetchone()[0] if cursor.fetchone() else "Unknown"
            cursor.execute("SELECT Sample FROM all_readings WHERE id = ?", (rec_id,))
            row = cursor.fetchone()
            sample = row[0] if row else "Unknown"
            print(f"  - Sample {sample}: ID {rec_id} ({mix}:{target})")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
