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


def get_readings_for_id(conn, original_id, source_table):
    """Get readings for a specific record from all_readings table"""
    cursor = conn.cursor()
    readings_columns = [f"readings{i}" for i in range(44)]
    readings_select = ", ".join(readings_columns)
    cursor.execute(f"SELECT {readings_select} FROM all_readings WHERE original_id = ? AND source_table = ?", (original_id, source_table))
    row = cursor.fetchone()
    if not row:
        return []
    readings = [r for r in row if r is not None]
    return readings


def get_azure_records_with_ar(conn, mix, mixtarget, limit=None):
    """
    Get records with both Azure and AR data for a mix-target, sorted by ranking disagreement.
    Uses all_readings table exclusively.

    Returns list of tuples:
    (original_id, Sample, File, AzureCls, AzureCFD, azure_order, ar_cls, ar_cfd, ar_order,
     source_table, azure_cls_label, ar_cls_label)
    """
    cursor = conn.cursor()

    # Build query to get records with both Azure and AR data from all_readings, sorted by ranking disagreement
    query = """
    SELECT
        original_id,
        Sample,
        File,
        AzureCls,
        AzureCFD,
        azure_order,
        ar_cls,
        ar_cfd,
        ar_order,
        source_table,
        AzureAmb,
        ar_amb,
        ABS(azure_order - ar_order) as rank_diff
    FROM all_readings
    WHERE Mix = ? AND MixTarget = ?
      AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
      AND azure_order IS NOT NULL AND ar_order IS NOT NULL
      AND in_use = 1
    ORDER BY rank_diff DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (mix, mixtarget))

    records = []
    for row in cursor.fetchall():
        orig_id, sample, file, azure_cls, azure_cfd, azure_order, ar_cls, ar_cfd, ar_order, source_table, azure_amb, ar_amb, rank_diff = row

        # Convert classifications to labels
        cls_labels = {0: 'NEG', 1: 'POS', 2: 'EQUIV', None: 'N/A'}

        # Determine Azure classification (amb overrides cls)
        if azure_amb == 1:
            azure_cls_calc = 2
        else:
            azure_cls_calc = azure_cls
        azure_cls_label = cls_labels.get(azure_cls_calc, 'N/A')

        # Determine AR classification (amb overrides cls)
        if ar_amb == 1:
            ar_cls_calc = 2
        else:
            ar_cls_calc = ar_cls
        ar_cls_label = cls_labels.get(ar_cls_calc, 'N/A')

        records.append((
            orig_id, sample, file, azure_cls_calc, azure_cfd, azure_order,
            ar_cls_calc, ar_cfd, ar_order, source_table,
            azure_cls_label, ar_cls_label
        ))

    return records


def get_classification_change_records(conn, mix, mixtarget, exclude_changes=None, limit=None):
    """
    Get records where classification changed between Azure and AR.
    Excludes rows where either AzureCls, AzureAmb, ar_cls, or ar_amb are NULL.

    Args:
        conn: Database connection
        mix: Mix name
        mixtarget: MixTarget name
        exclude_changes: List of change types to exclude (e.g., ['pos->neg', 'neg->pos'])
        limit: Maximum number of records per change type to return

    Returns list of tuples:
    (original_id, Sample, File, AzureCls, AzureCFD, AzureAmb, ar_cls, ar_cfd, ar_amb,
     source_table, azure_cls_label, ar_cls_label, change_type, cfd_diff)
    """
    cursor = conn.cursor()

    # Query with all four columns NOT NULL
    query = """
    SELECT
        original_id,
        Sample,
        File,
        AzureCls,
        AzureCFD,
        AzureAmb,
        ar_cls,
        ar_cfd,
        ar_amb,
        source_table
    FROM all_readings
    WHERE Mix = ? AND MixTarget = ?
      AND AzureCls IS NOT NULL AND AzureAmb IS NOT NULL
      AND ar_cls IS NOT NULL AND ar_amb IS NOT NULL
      AND in_use = 1
    """

    cursor.execute(query, (mix, mixtarget))

    # Classification labels
    cls_labels = {0: 'NEG', 1: 'POS', 2: 'EQUIV'}

    records = []
    for row in cursor.fetchall():
        orig_id, sample, file, azure_cls, azure_cfd, azure_amb, ar_cls, ar_cfd, ar_amb, source_table = row

        # Calculate effective classifications (amb=1 overrides cls)
        azure_cls_calc = 2 if azure_amb == 1 else azure_cls
        ar_cls_calc = 2 if ar_amb == 1 else ar_cls

        # Skip if classifications match
        if azure_cls_calc == ar_cls_calc:
            continue

        # Determine change type
        azure_label = cls_labels[azure_cls_calc]
        ar_label = cls_labels[ar_cls_calc]
        change_type = f"{azure_label.lower()}->{ar_label.lower()}"

        # Skip if this change type is excluded
        if exclude_changes and change_type in exclude_changes:
            continue

        cfd_diff = abs(azure_cfd - ar_cfd)

        records.append((
            orig_id, sample, file, azure_cls_calc, azure_cfd, azure_amb,
            ar_cls_calc, ar_cfd, ar_amb, source_table,
            azure_label, ar_label, change_type, cfd_diff
        ))

    # Sort by change type, then by CFD difference descending
    records.sort(key=lambda x: (x[12], -x[13]))

    # Apply limit if specified - apply limit PER change type
    if limit:
        limited_records = []
        change_type_counts = {}
        for record in records:
            change_type = record[12]
            if change_type not in change_type_counts:
                change_type_counts[change_type] = 0

            if change_type_counts[change_type] < limit:
                limited_records.append(record)
                change_type_counts[change_type] += 1

        records = limited_records

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


def generate_comparison_report(conn, output_file, compare_count=None, include_ic=True, show_classification_changes=False, exclude_change_type=None, sort_by='azure_cfd', mixes=None):
    """
    Generate comparison report of Azure vs AR results.

    Args:
        conn: Database connection
        output_file: Output HTML file path
        compare_count: Limit samples per change type (default: None = show all)
        include_ic: Include IC targets (default: False, exclude IC)
        show_classification_changes: Show classification changes instead of ranking disagreements
        exclude_change_type: List of change types to exclude (e.g., ['pos->neg'])
        sort_by: Sort records within groups by 'azure_cfd' or 'ar_cfd' (default: 'azure_cfd')
        mixes: Set of mix names to include (default: None = all mixes)
    """

    # Get mix-target combinations (exclude IC if specified, filter by mixes if specified)
    cursor = conn.cursor()
    ic_filter = "" if include_ic else "AND MixTarget != 'IC'"

    # Build mixes filter
    if mixes:
        placeholders = ','.join('?' * len(mixes))
        mix_filter = f"AND Mix IN ({placeholders})"
        query_params = list(mixes)
    else:
        mix_filter = ""
        query_params = []

    cursor.execute(f"""
        SELECT DISTINCT Mix, MixTarget
        FROM all_readings
        WHERE AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
              {ic_filter}
              {mix_filter}
        ORDER BY Mix, MixTarget
    """, query_params)

    combinations = cursor.fetchall()

    # Determine report title and header text based on mode
    if show_classification_changes:
        report_title = "Azure vs AR Classification Changes Report"
        report_subtitle = "Classification differences between algorithms"
        header_note = "Showing samples where classification differs between Azure and AR algorithms"
    else:
        report_title = "Azure vs AR Comparison Report"
        report_subtitle = "Top disagreement samples per Mix-Target combination"
        header_note = """
        <div class="warning">
            <strong>⚠️ Key Finding:</strong> AR and Azure CFD scales appear inverted!
            <br/>AR ranks POS controls LOW (correctly by CFD polarity) but Azure ranks them HIGH (opposite)
            <br/>This suggests AR uses opposite CFD polarity convention vs Azure
        </div>
        """

    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{report_title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
            }}
            .header {{
                text-align: center;
                margin: 20px 0;
            }}
            h1 {{
                text-align: center;
                margin: 30px 0 20px 0;
                padding: 20px;
                background: #2c3e50;
                color: white;
                border-radius: 8px;
                font-size: 1.8em;
            }}
            h2 {{
                text-align: center;
                margin: 30px 0 15px 0;
                padding: 15px;
                background: #34495e;
                color: white;
                border-radius: 8px;
                font-size: 1.4em;
            }}
            h3 {{
                text-align: left;
                margin: 20px 0 10px 0;
                padding: 10px;
                background: #5d6d7b;
                color: white;
                border-radius: 4px;
                font-size: 1.1em;
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
                font-size: 10px;
                margin-bottom: 4px;
                color: #333;
                font-weight: bold;
            }}
            .result-box {{
                font-size: 8px;
                margin-top: 6px;
                padding: 6px;
                background: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                text-align: center;
                line-height: 1.4;
            }}
            .result-box .label {{
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 4px;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 3px;
            }}
            .result-box .azure {{
                color: #3498db;
                font-weight: bold;
                margin-top: 3px;
            }}
            .result-box .ar {{
                color: #e67e22;
                font-weight: bold;
                margin-top: 3px;
            }}
            .rank-diff {{
                font-size: 7px;
                color: #c0392b;
                font-weight: bold;
                margin-top: 4px;
                padding-top: 3px;
                border-top: 1px solid #bdc3c7;
            }}
            .cfd-diff {{
                font-size: 7px;
                color: #2980b9;
                font-weight: bold;
                margin-top: 4px;
                padding-top: 3px;
                border-top: 1px solid #bdc3c7;
            }}
            .stats {{
                grid-column: 1 / -1;
                text-align: center;
                margin: 10px 0;
                padding: 10px;
                background: #ecf0f1;
                border-radius: 4px;
                color: #2c3e50;
            }}
            .warning {{
                color: #c0392b;
                font-size: 0.9em;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{report_title}</h1>
            <p style="color: #666;">{report_subtitle}</p>
            {header_note}
        </div>
        <div class="container">
    '''

    print(f"Generating {report_title} for {len(combinations)} mix-target combinations...")

    for mix, mixtarget in combinations:
        print(f"  Processing {mix}-{mixtarget}...")

        if show_classification_changes:
            # Get classification change records
            records = get_classification_change_records(conn, mix, mixtarget, exclude_changes=exclude_change_type, limit=compare_count)
            if not records:
                continue

            html_content += f'<h2>{mix} - {mixtarget}</h2>'

            # Group by change type
            changes_dict = {}
            for record in records:
                change_type = record[12]
                if change_type not in changes_dict:
                    changes_dict[change_type] = []
                changes_dict[change_type].append(record)

            # Display each change type as a section
            for change_type in sorted(changes_dict.keys()):
                change_records = changes_dict[change_type]

                # Sort records within this change type group based on sort_by parameter
                if sort_by == 'ar_cfd':
                    # ar_cfd is at index 7 in the record tuple
                    change_records = sorted(change_records, key=lambda x: x[7], reverse=True)
                else:  # default: azure_cfd
                    # azure_cfd is at index 4 in the record tuple
                    change_records = sorted(change_records, key=lambda x: x[4], reverse=True)

                html_content += f'<h3>Classification Change: {change_type.upper()}</h3>'
                html_content += f'''
                <div class="stats">
                    {len(change_records)} samples with {change_type} change, sorted by CFD difference
                </div>
                '''

                for orig_id, sample, file, azure_cls, azure_cfd, azure_amb, ar_cls, ar_cfd, ar_amb, source_table, azure_label, ar_label, change_type_str, cfd_diff in change_records:
                    try:
                        readings = get_readings_for_id(conn, orig_id, source_table)
                        if not readings:
                            continue

                        metadata = {
                            'AzureCls': azure_cls,
                            'AzureCFD': azure_cfd,
                            'Sample': sample,
                            'File': file
                        }

                        svg_graph, _ = generate_svg_graph(orig_id, readings, metadata)

                        result_html = f'''
                        <div class="result-box">
                            <div class="label">AZURE vs AR</div>
                            <div class="azure">
                                Azure: {azure_label}<br/>CFD: {azure_cfd:.2f}
                            </div>
                            <div class="ar">
                                AR: {ar_label}<br/>CFD: {ar_cfd:.2f}
                            </div>
                            <div class="cfd-diff">Δ CFD: {cfd_diff:.2f}</div>
                        </div>
                        '''

                        combined = svg_graph.rstrip() + '\n' + result_html
                        html_content += combined

                    except Exception as e:
                        print(f"    Error processing record {orig_id}: {e}")
                        continue

        else:
            # Original ranking-based mode
            records = get_azure_records_with_ar(conn, mix, mixtarget, limit=compare_count)
            if not records:
                continue

            html_content += f'''
                <h2>{mix} - {mixtarget}</h2>
                <div class="stats">
                    Showing top {len(records)} samples with largest ranking disagreements
                </div>
            '''

            for orig_id, sample, file, azure_cls, azure_cfd, azure_order, ar_cls, ar_cfd, ar_order, source_table, azure_cls_label, ar_cls_label in records:
                try:
                    readings = get_readings_for_id(conn, orig_id, source_table)
                    if not readings:
                        continue

                    rank_diff = abs(azure_order - ar_order)

                    metadata = {
                        'AzureCls': azure_cls,
                        'AzureCFD': azure_cfd,
                        'Sample': sample,
                        'File': file
                    }

                    svg_graph, _ = generate_svg_graph(orig_id, readings, metadata)

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

                    combined = svg_graph.rstrip() + '\n' + result_html
                    html_content += combined

                except Exception as e:
                    print(f"    Error processing record {orig_id}: {e}")
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
    parser.add_argument('--compare-az-ar', type=int, default=None,
                       help='Limit number of samples per change type to show (default: show all)')
    parser.add_argument('--no-ic', action='store_true',
                       help='Exclude IC (internal control) targets (default: included)')
    parser.add_argument('--show-classification-changes', action='store_true',
                       help='Show classification changes instead of ranking disagreements')
    parser.add_argument('--exclude-change-type', nargs='+',
                       choices=['pos->neg', 'neg->pos', 'pos->amb', 'neg->amb', 'amb->pos', 'amb->neg'],
                       help='Exclude specific change types (e.g., pos->neg neg->pos)')
    parser.add_argument('--sort-by', choices=['azure_cfd', 'ar_cfd'], default='azure_cfd',
                       help='Sort records within groups by: azure_cfd (Azure CFD), ar_cfd (AR CFD) (default: azure_cfd)')
    parser.add_argument('--mixes',
                       help='Comma-separated list of mix names to include (default: all mixes)')

    args = parser.parse_args()

    # Expand database path
    db_path = Path(args.db).expanduser()

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(str(db_path))

    include_ic = not args.no_ic
    exclude_changes = set(args.exclude_change_type) if args.exclude_change_type else None

    # Parse mixes filter
    mixes = None
    if args.mixes:
        # Split by comma, strip whitespace, convert to uppercase
        mixes = {mix.strip().upper() for mix in args.mixes.split(',')}
        print(f"Filtering to mixes: {', '.join(sorted(mixes))}")

    # Generate report
    generate_comparison_report(
        conn,
        args.output,
        compare_count=args.compare_az_ar,
        include_ic=include_ic,
        show_classification_changes=args.show_classification_changes,
        exclude_change_type=exclude_changes,
        sort_by=args.sort_by,
        mixes=mixes
    )

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
