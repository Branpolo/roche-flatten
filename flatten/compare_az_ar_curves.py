#!/usr/bin/env python3
"""
Generate comparison report of Azure vs AR classification results.

Shows sample curves with both Azure and AR classifications, organized by Mix-Target.
Includes top N samples with largest ranking disagreements per target for detailed analysis.
"""

import sqlite3
import argparse
import sys
from pathlib import Path


def get_readings_for_id(conn, record_id, table='readings'):
    """Get readings for a specific ID"""
    cursor = conn.cursor()
    readings_columns = [f"readings{i}" for i in range(44)]
    readings_select = ", ".join(readings_columns)
    cursor.execute(f"SELECT {readings_select} FROM {table} WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if not row:
        return []
    readings = [r for r in row if r is not None]
    return readings


def get_azure_records_with_ar(conn, mix, mixtarget, limit=None):
    """
    Get records with both Azure and AR data for a mix-target, sorted by ranking disagreement.

    Returns list of tuples:
    (id, Sample, File, AzureCls, AzureCFD, azure_order, ar_cls, ar_cfd, ar_order,
     source_table, azure_cls_label, ar_cls_label)
    """
    cursor = conn.cursor()

    # Build query to get records with both Azure and AR data, sorted by ranking disagreement
    query = f"""
    SELECT
        id,
        Sample,
        File,
        AzureCls,
        AzureCFD,
        azure_order,
        ar_cls,
        ar_cfd,
        ar_order,
        source_table
    FROM (
        SELECT
            id,
            Sample,
            File,
            AzureCls,
            AzureCFD,
            azure_order,
            ar_cls,
            ar_cfd,
            ar_order,
            'readings' as source_table,
            ABS(azure_order - ar_order) as rank_diff
        FROM readings
        WHERE Mix = ? AND MixTarget = ?
          AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
          AND azure_order IS NOT NULL AND ar_order IS NOT NULL
          AND in_use = 1

        UNION ALL

        SELECT
            id,
            Sample,
            File,
            AzureCls,
            AzureCFD,
            azure_order,
            ar_cls,
            ar_cfd,
            ar_order,
            'test_data' as source_table,
            ABS(azure_order - ar_order) as rank_diff
        FROM test_data
        WHERE Mix = ? AND MixTarget = ?
          AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
          AND azure_order IS NOT NULL AND ar_order IS NOT NULL
          AND in_use = 1
    )
    ORDER BY rank_diff DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (mix, mixtarget, mix, mixtarget))

    records = []
    for row in cursor.fetchall():
        rec_id, sample, file, azure_cls, azure_cfd, azure_order, ar_cls, ar_cfd, ar_order, source_table = row

        # Convert classifications to labels
        cls_labels = {0: 'NEG', 1: 'POS', 2: 'EQUIV', None: 'N/A'}
        azure_cls_label = cls_labels.get(azure_cls, 'N/A')

        # Calculate AR classification (like AR system does: if ar_amb==1, cls=2)
        ar_amb = None
        if ar_cfd is not None:
            # We need to get ar_amb from database
            cursor.execute(f"SELECT ar_amb FROM {source_table} WHERE id = ?", (rec_id,))
            amb_row = cursor.fetchone()
            if amb_row:
                ar_amb = amb_row[0]

        # Determine AR classification
        if ar_amb == 1:
            ar_cls_calc = 2
        else:
            ar_cls_calc = ar_cls

        ar_cls_label = cls_labels.get(ar_cls_calc, 'N/A')

        records.append((
            rec_id, sample, file, azure_cls, azure_cfd, azure_order,
            ar_cls_calc, ar_cfd, ar_order, source_table,
            azure_cls_label, ar_cls_label
        ))

    return records


def generate_svg_graph(record_id, readings, metadata, width=240, height=180):
    """
    Generate SVG graph showing the curve.

    Args:
        record_id: Record identifier
        readings: Sample readings
        metadata: Sample metadata dict
        width: SVG width
        height: SVG height
    """
    margin = 30
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    padding_ratio = 0.06

    if not readings or len(readings) < 2:
        return f'<div style="color: red;">No data for ID {record_id}</div>'

    main_min = min(readings)
    main_max = max(readings)
    value_range = main_max - main_min

    if value_range == 0:
        adjustment = max(abs(main_max) * 0.1, 1)
        min_display = main_min - (adjustment / 2)
        max_display = main_max + (adjustment / 2)
    else:
        padding = value_range * padding_ratio
        min_display = main_min - padding
        max_display = main_max + padding

    reading_range = max(max_display - min_display, 1e-6)

    def generate_polyline(readings_data, value_min, value_range):
        """Generate polyline points for a set of readings"""
        points = []
        steps = max(len(readings_data) - 1, 1)
        for i, reading in enumerate(readings_data):
            x = margin + (i * plot_width / steps)
            normalized = (reading - value_min) / value_range
            y = margin + plot_height - (plot_height * normalized)
            points.append(f"{x:.1f},{y:.1f}")
        return " ".join(points)

    # Generate main sample polyline
    main_polyline = generate_polyline(readings, min_display, reading_range)

    # Determine color based on AzureCls
    cls_colors = {
        0: '#2ecc71',  # Green for Negative
        1: '#e74c3c',  # Red for Positive
        2: '#f39c12'   # Orange for Ambiguous
    }
    main_color = cls_colors.get(metadata['AzureCls'], '#95a5a6')

    # Build header text
    sample_label = str(metadata.get('Sample', 'N/A') or 'N/A')
    file_label = str(metadata.get('File', 'N/A') or 'N/A')
    header_text = f"{sample_label} | {file_label[:12]}..."

    svg = f'''
    <div class="graph-container">
        <div class="graph-header">
            {header_text}
        </div>
        <svg width="{width}" height="{height}" style="background: white;">
            <!-- Grid lines -->
            <line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#ddd" stroke-width="1"/>
            <line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#ddd" stroke-width="1"/>

            <!-- Main sample curve -->
            <polyline points="{main_polyline}" fill="none" stroke="{main_color}" stroke-width="2"/>

            <!-- Y-axis labels -->
            <text x="{margin-5}" y="{margin+5}" text-anchor="end" font-size="10" fill="#666">{max_display:.0f}</text>
            <text x="{margin-5}" y="{height-margin+5}" text-anchor="end" font-size="10" fill="#666">{min_display:.0f}</text>
        </svg>
    </div>
    '''
    return svg, metadata


def generate_comparison_report(conn, output_file, compare_count=10, include_ic=True):
    """
    Generate comparison report of Azure vs AR results.

    Args:
        conn: Database connection
        output_file: Output HTML file path
        compare_count: Number of top disagreement samples per target to show
        include_ic: Include IC targets (default: False, exclude IC)
    """

    # Get mix-target combinations (exclude IC if specified)
    cursor = conn.cursor()
    ic_filter = "" if include_ic else "AND MixTarget != 'IC'"
    cursor.execute(f"""
        SELECT DISTINCT Mix, MixTarget
        FROM readings
        WHERE AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL AND azure_order IS NOT NULL
              {ic_filter}
        ORDER BY Mix, MixTarget
    """)

    combinations = cursor.fetchall()

    html_content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Azure vs AR Comparison Report</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
            }
            .header {
                text-align: center;
                margin: 20px 0;
            }
            h1 {
                text-align: center;
                margin: 30px 0 20px 0;
                padding: 20px;
                background: #2c3e50;
                color: white;
                border-radius: 8px;
                font-size: 1.8em;
            }
            h2 {
                text-align: center;
                margin: 30px 0 15px 0;
                padding: 15px;
                background: #34495e;
                color: white;
                border-radius: 8px;
                font-size: 1.4em;
            }
            .container {
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 8px;
                max-width: 1400px;
                margin: 0 auto;
            }
            .graph-container {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
                text-align: center;
            }
            .graph-header {
                font-size: 10px;
                margin-bottom: 4px;
                color: #333;
                font-weight: bold;
            }
            .result-box {
                font-size: 8px;
                margin-top: 6px;
                padding: 6px;
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                text-align: center;
                line-height: 1.4;
            }
            .result-box .label {
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 4px;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 3px;
            }
            .result-box .azure {
                color: #3498db;
                font-weight: bold;
                margin-top: 3px;
            }
            .result-box .ar {
                color: #e67e22;
                font-weight: bold;
                margin-top: 3px;
            }
            .rank-diff {
                font-size: 7px;
                color: #c0392b;
                font-weight: bold;
                margin-top: 4px;
                padding-top: 3px;
                border-top: 1px solid #bdc3c7;
            }
            .stats {
                grid-column: 1 / -1;
                text-align: center;
                margin: 10px 0;
                padding: 10px;
                background: #ecf0f1;
                border-radius: 4px;
                color: #2c3e50;
            }
            .warning {
                color: #c0392b;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Azure vs AR Comparison Report</h1>
            <p style="color: #666;">Top disagreement samples per Mix-Target combination</p>
            <div class="warning">
                <strong>⚠️ Key Finding:</strong> AR and Azure CFD scales appear inverted!
                <br/>AR ranks POS controls LOW (correctly by CFD polarity) but Azure ranks them HIGH (opposite)
                <br/>This suggests AR uses opposite CFD polarity convention vs Azure
            </div>
        </div>
        <div class="container">
    '''

    print(f"Generating comparison report for {len(combinations)} mix-target combinations...")

    for mix, mixtarget in combinations:
        print(f"  Processing {mix}-{mixtarget}...")

        # Get top comparison samples
        records = get_azure_records_with_ar(conn, mix, mixtarget, limit=compare_count)

        if not records:
            continue

        html_content += f'''
            <h2>{mix} - {mixtarget}</h2>
            <div class="stats">
                Showing top {len(records)} samples with largest ranking disagreements
            </div>
        '''

        for rec_id, sample, file, azure_cls, azure_cfd, azure_order, ar_cls, ar_cfd, ar_order, source_table, azure_cls_label, ar_cls_label in records:
            try:
                readings = get_readings_for_id(conn, rec_id, source_table)
                if not readings:
                    continue

                rank_diff = abs(azure_order - ar_order)

                metadata = {
                    'AzureCls': azure_cls,
                    'AzureCFD': azure_cfd,
                    'Sample': sample,
                    'File': file
                }

                svg_graph, _ = generate_svg_graph(rec_id, readings, metadata)

                # Build result box - OUTSIDE the container div
                result_html = f'''
                <div class="result-box">
                    <div class="label">AZURE vs AR</div>
                    <div class="azure">
                        Azure: {azure_cls_label}<br/>CFD: {azure_cfd:.2f}<br/>Rank: {azure_order}
                    </div>
                    <div class="ar">
                        AR: {ar_cls_label}<br/>CFD: {ar_cfd:.2f}<br/>Rank: {ar_order}
                    </div>
                    <div class="rank-diff">Δ Rank: {rank_diff}</div>
                </div>
                '''

                # Combine SVG and results
                combined = svg_graph.rstrip() + '\n' + result_html

                html_content += combined

            except Exception as e:
                print(f"    Error processing record {rec_id}: {e}")
                continue

    html_content += '''
        </div>
    </body>
    </html>
    '''

    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"\nHTML report generated: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate comparison report of Azure vs AR classification results'
    )
    parser.add_argument('--db', default='~/dbs/readings.db',
                       help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--output', default='output_data/az_ar_comparison.html',
                       help='Output HTML file path (default: output_data/az_ar_comparison.html)')
    parser.add_argument('--compare-az-ar', type=int, default=10,
                       help='Number of top disagreement samples per mix-target to show (default: 10)')
    parser.add_argument('--no-ic', action='store_true',
                       help='Exclude IC (internal control) targets (default: included)')

    args = parser.parse_args()

    # Expand database path
    db_path = Path(args.db).expanduser()

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(str(db_path))

    include_ic = not args.no_ic

    # Generate report
    generate_comparison_report(
        conn,
        args.output,
        compare_count=args.compare_az_ar,
        include_ic=include_ic
    )

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
