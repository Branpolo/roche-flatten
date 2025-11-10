#!/usr/bin/env python3
"""
Generate HTML report of Azure classification results.

This script creates an HTML report organized by Mix and MixTarget,
showing original curves (no flattening) grouped by Azure classification
(Positive, Negative, Ambiguous) and sorted by confidence (AzureCFD).
"""

import sqlite3
import argparse
import sys
from pathlib import Path
from tqdm import tqdm


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


def get_positive_control_samples(conn, mix, mixtarget):
    """
    Get positive control sample identifiers for a given mix-target combination.

    Args:
        conn: Database connection
        mix: Mix name (case-insensitive)
        mixtarget: MixTarget name (case-insensitive, e.g., "Adeno", "Rota")

    Returns:
        List of control sample names
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT control_sample
        FROM pos_controls
        WHERE LOWER(mix) = LOWER(?)
          AND UPPER(target) = UPPER(?)
    """, (mix, mixtarget))
    return [row[0] for row in cursor.fetchall()]


def get_control_curves(conn, file_uid, mix, mixtarget, control_samples, is_positive=True):
    """
    Get control curves matching the criteria.

    Args:
        conn: Database connection
        file_uid: File identifier to match
        mix: Mix name
        mixtarget: MixTarget name (e.g., "Adeno", "Rota")
        control_samples: List of sample names (for positive) or None (for negative)
        is_positive: True for positive controls, False for negative controls

    Returns:
        List of tuples: (record_id, sample_name, readings, source_table)
    """
    cursor = conn.cursor()
    readings_columns = [f"readings{i}" for i in range(44)]
    readings_select = ", ".join(readings_columns)

    controls = []

    # Query both tables
    for table in ['readings', 'test_data']:
        if is_positive and control_samples:
            # Positive controls: match specific sample names (case-insensitive)
            # Build UPPER comparison for each control sample
            conditions = ' OR '.join([f'UPPER(Sample) = UPPER(?)' for _ in control_samples])
            query = f"""
                SELECT id, Sample, {readings_select}
                FROM {table}
                WHERE FileUID = ?
                  AND Mix = ?
                  AND UPPER(MixTarget) = UPPER(?)
                  AND ({conditions})
                  AND in_use = 1
            """
            params = [file_uid, mix, mixtarget] + control_samples
        else:
            # Negative controls: pattern matching (case-insensitive)
            query = f"""
                SELECT id, Sample, {readings_select}
                FROM {table}
                WHERE FileUID = ?
                  AND Mix = ?
                  AND UPPER(MixTarget) = UPPER(?)
                  AND (UPPER(Sample) LIKE 'NPC%' OR UPPER(Sample) LIKE 'NTC%' OR UPPER(Sample) LIKE 'NEG%')
                  AND in_use = 1
            """
            params = [file_uid, mix, mixtarget]

        cursor.execute(query, params)
        for row in cursor.fetchall():
            record_id = row[0]
            sample = row[1]
            readings = [r for r in row[2:] if r is not None]
            if readings:  # Only include if we have actual data
                controls.append((record_id, sample, readings, table))

    return controls


def get_sample_detail_records(conn, sample_ids):
    """
    Get all records for specified samples with Azure and Embed results.

    For sample details mode: Show ALL targets including IC, grouped by Mix/MixTarget.
    Skip E1, E2 targets. Include File info for run identification.

    Args:
        conn: Database connection
        sample_ids: List of sample IDs to retrieve

    Returns:
        List of tuples: (id, Sample, File, Mix, MixTarget, Target, AzureCls, AzureCFD,
                        EmbedCls, EmbedCt, source_table)
    """
    cursor = conn.cursor()

    # Convert sample IDs to string list for SQL
    sample_list = ', '.join([f"'{s}'" for s in sample_ids])

    # Query both tables with all targets (including IC), skip E1/E2
    cursor.execute(f"""
    SELECT * FROM (
        SELECT
            id,
            Sample,
            File,
            Mix,
            MixTarget,
            Target,
            AzureCls,
            AzureCFD,
            EmbedCls,
            EmbedCt,
            'readings' as source_table
        FROM readings
        WHERE Sample IN ({sample_list})
          AND in_use = 1
          AND MixTarget NOT IN ('E1', 'E2')

        UNION ALL

        SELECT
            id,
            Sample,
            File,
            Mix,
            MixTarget,
            Target,
            AzureCls,
            AzureCFD,
            EmbedCls,
            EmbedCt,
            'test_data' as source_table
        FROM test_data
        WHERE Sample IN ({sample_list})
          AND in_use = 1
          AND MixTarget NOT IN ('E1', 'E2')
    )
    ORDER BY
        Sample,
        File,
        Mix,
        MixTarget,
        Target
    """)

    return cursor.fetchall()


def get_azure_records(conn, include_ic=False, compare_embed=False):
    """
    Get all records with Azure classification results from BOTH readings and test_data.

    When compare_embed=False: Sorted by Mix, MixTarget, AzureCls (1,0,2), AzureCFD
    When compare_embed=True: Sorted by comparison category, Mix, MixTarget, AzureCls, AzureCFD

    Args:
        include_ic: If False (default), exclude IC (internal control) targets
        compare_embed: If True, order by comparison category first

    Returns:
        List of tuples: (id, Mix, MixTarget, Target, AzureCls, AzureCFD, Sample,
                        File, FileUID, Tube, EmbedCls, EmbedCt, source_table)
    """
    cursor = conn.cursor()

    # Build WHERE clause for IC filtering
    ic_filter = "" if include_ic else "AND MixTarget NOT LIKE '%IC%'"

    # Build ORDER BY clause based on compare_embed mode
    if compare_embed:
        # Primary sort by comparison category: DISCREPANT, EQUIVOCAL, AGREED, NO_EMBED
        order_by = """
        ORDER BY
            -- Comparison category order: DISCREPANT, EQUIVOCAL, AGREED, NO_EMBED
            CASE
                WHEN AzureCls = 2 THEN 2  -- EQUIVOCAL
                WHEN AzureCls IS NOT NULL AND AzureCls != 2 AND EmbedCls IS NOT NULL AND EmbedCls != AzureCls THEN 1  -- DISCREPANT
                WHEN AzureCls IS NOT NULL AND EmbedCls IS NOT NULL THEN 3  -- AGREED
                WHEN AzureCls IS NOT NULL AND EmbedCls IS NULL THEN 4  -- NO_EMBED
                ELSE 5
            END,
            Mix,
            MixTarget,
            CASE AzureCls
                WHEN 1 THEN 1  -- Positive first
                WHEN 2 THEN 2  -- Ambiguous second
                WHEN 0 THEN 3  -- Negative third
                ELSE 4
            END,
            AzureCFD ASC  -- Low confidence first within each class
        """
    else:
        # Original ordering: Mix, MixTarget, AzureCls, AzureCFD
        order_by = """
        ORDER BY
            Mix,
            MixTarget,
            CASE AzureCls
                WHEN 1 THEN 1  -- Positive first
                WHEN 2 THEN 2  -- Ambiguous second
                WHEN 0 THEN 3  -- Negative third
                ELSE 4
            END,
            AzureCFD ASC  -- Low confidence first within each class
        """

    # Query both tables and combine results
    cursor.execute(f"""
    SELECT * FROM (
        SELECT
            id,
            Mix,
            MixTarget,
            Target,
            AzureCls,
            AzureCFD,
            Sample,
            File,
            FileUID,
            Tube,
            EmbedCls,
            EmbedCt,
            'readings' as source_table
        FROM readings
        WHERE AzureCls IS NOT NULL
          AND AzureCFD IS NOT NULL
          AND in_use = 1
          {ic_filter}

        UNION ALL

        SELECT
            id,
            Mix,
            MixTarget,
            Target,
            AzureCls,
            AzureCFD,
            Sample,
            File,
            FileUID,
            Tube,
            EmbedCls,
            EmbedCt,
            'test_data' as source_table
        FROM test_data
        WHERE AzureCls IS NOT NULL
          AND AzureCFD IS NOT NULL
          AND in_use = 1
          {ic_filter}
    )
    {order_by}
    """)

    return cursor.fetchall()


def classify_comparison(azure_cls, embed_cls):
    """
    Classify a record based on comparison between Azure and embedded machine classifications.

    Args:
        azure_cls: Azure classification (0=Negative, 1=Positive, 2=Ambiguous, None=Not classified)
        embed_cls: Embedded machine classification (0=Negative, 1=Positive, None=Not classified)

    Returns:
        str: One of 'DISCREPANT', 'EQUIVOCAL', 'AGREED', 'NO_EMBED'
    """
    # EQUIVOCAL: Azure says ambiguous
    if azure_cls == 2:
        return 'EQUIVOCAL'

    # NO_EMBED: Has Azure classification but no machine result
    if azure_cls is not None and embed_cls is None:
        return 'NO_EMBED'

    # DISCREPANT: Azure disagrees with machine (excluding ambiguous/null cases)
    if azure_cls is not None and azure_cls != 2 and embed_cls is not None and embed_cls != azure_cls:
        return 'DISCREPANT'

    # AGREED: Everything else (Azure agrees with machine)
    return 'AGREED'


def generate_svg_graph(record_id, readings, metadata, width=240, height=180, show_cfd=False,
                       pos_controls=None, neg_controls=None, show_machine_result=False):
    """
    Generate SVG graph showing the original curve with optional control curves.

    Args:
        record_id: Record identifier
        readings: Main sample readings
        metadata: Sample metadata dict (includes EmbedCls, EmbedCt if available)
        width: SVG width
        height: SVG height
        show_cfd: Show CFD value
        pos_controls: List of tuples (sample_name, readings) for positive controls
        neg_controls: List of tuples (sample_name, readings) for negative controls
        show_machine_result: Show embedded machine result (POS/NEG with CT)
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

    def format_readings(readings_data):
        return ",".join(f"{float(val):.6f}" for val in readings_data)

    # Generate main sample polyline
    main_polyline = generate_polyline(readings, min_display, reading_range)

    # Determine color based on AzureCls
    cls_colors = {
        0: '#2ecc71',  # Green for Negative/Unaffected
        1: '#e74c3c',  # Red for Positive/Affected
        2: '#f39c12'   # Orange for Ambiguous
    }
    main_color = cls_colors.get(metadata['AzureCls'], '#95a5a6')

    # Build header text
    header_text = f"{metadata['Sample']} | {metadata['File'][:12]}... | {metadata['Tube']}"

    # Optional CFD overlay
    cfd_overlay = ''
    if show_cfd:
        cfd_overlay = f'''
            <text x="{width-5}" y="12" text-anchor="end" font-size="9" fill="#999" font-weight="bold">CFD:{metadata['AzureCFD']:.2f}</text>
        '''

    # Generate control curve polylines
    control_polylines = ''
    legend_items = []

    # Positive controls (blue, dashed)
    if pos_controls:
        for sample_name, ctrl_readings in pos_controls:
            polyline = generate_polyline(ctrl_readings, min_display, reading_range)
            control_polylines += f'''
            <polyline points="{polyline}" fill="none" stroke="#3498db" stroke-width="1.5"
                      stroke-dasharray="5,3" class="control-curve hidden" data-control-type="positive"
                      data-readings="{format_readings(ctrl_readings)}"/>
            '''
        legend_items.append('<span style="color:#3498db;">━━ Pos Ctrl</span>')

    # Negative controls (gray, dotted)
    if neg_controls:
        for sample_name, ctrl_readings in neg_controls:
            polyline = generate_polyline(ctrl_readings, min_display, reading_range)
            control_polylines += f'''
            <polyline points="{polyline}" fill="none" stroke="#95a5a6" stroke-width="1.5"
                      stroke-dasharray="2,2" class="control-curve hidden" data-control-type="negative"
                      data-readings="{format_readings(ctrl_readings)}"/>
            '''
        legend_items.append('<span style="color:#95a5a6;">··· Neg Ctrl</span>')

    # Build legend HTML
    legend_html = ''
    if legend_items:
        legend_html = f'''
        <div class="graph-legend" style="font-size: 8px; margin-top: 2px; text-align: center;">
            {' | '.join(legend_items)}
        </div>
        '''

    # Build machine result HTML
    machine_result_html = ''
    if show_machine_result and 'EmbedCls' in metadata:
        embed_cls = metadata.get('EmbedCls')
        embed_ct = metadata.get('EmbedCt')

        if embed_cls is not None:
            if embed_cls == 1:  # Positive
                if embed_ct is not None:
                    machine_result_html = f'''
        <div class="machine-result" style="font-size: 9px; margin-top: 4px; text-align: center; font-weight: bold; color: #e74c3c;">
            MACHINE RESULT: POS (CT: {embed_ct:.2f})
        </div>
        '''
                else:
                    machine_result_html = f'''
        <div class="machine-result" style="font-size: 9px; margin-top: 4px; text-align: center; font-weight: bold; color: #e74c3c;">
            MACHINE RESULT: POS
        </div>
        '''
            elif embed_cls == 0:  # Negative
                machine_result_html = f'''
        <div class="machine-result" style="font-size: 9px; margin-top: 4px; text-align: center; font-weight: bold; color: #2ecc71;">
            MACHINE RESULT: NEG
        </div>
        '''

    svg = f'''
    <div class="graph-container">
        <div class="graph-header">
            {header_text}
        </div>
        <svg width="{width}" height="{height}" style="background: white;" data-margin="{margin}">
            <!-- Grid lines -->
            <line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#ddd" stroke-width="1"/>
            <line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#ddd" stroke-width="1"/>

            <!-- Control curves (drawn first, behind main curve) -->
            {control_polylines}

            <!-- Main sample curve -->
            <polyline points="{main_polyline}" fill="none" stroke="{main_color}" stroke-width="2"
                      class="main-curve" data-readings="{format_readings(readings)}"/>

            <!-- Y-axis labels -->
            <text class="y-axis-max" x="{margin-5}" y="{margin+5}" text-anchor="end" font-size="10" fill="#666">{max_display:.0f}</text>
            <text class="y-axis-min" x="{margin-5}" y="{height-margin+5}" text-anchor="end" font-size="10" fill="#666">{min_display:.0f}</text>

            {cfd_overlay}
        </svg>
        {legend_html}
        {machine_result_html}
    </div>
    '''
    return svg


def generate_sample_details_report(conn, records, output_file, show_cfd=False, scale_y_axis=True):
    """
    Generate HTML report for sample details mode.

    Shows all targets for specified samples with both Azure and Embed results side-by-side.
    Organized by Sample → Mix → MixTarget.

    Args:
        conn: Database connection
        records: List of records from get_sample_detail_records
        output_file: Output HTML file path
        show_cfd: Show confidence values
        scale_y_axis: Rescale y-axis when toggling controls (default: True)
    """

    html_content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sample Details Report</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
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
            .result-overlay {
                font-size: 9px;
                margin-top: 4px;
                padding: 4px;
                background: #ecf0f1;
                border-radius: 3px;
                text-align: center;
            }
            .result-overlay .label {
                font-weight: bold;
                color: #2c3e50;
            }
            .result-overlay .azure {
                color: #3498db;
            }
            .result-overlay .embed {
                color: #e67e22;
            }
            .header {
                text-align: center;
                margin: 20px 0;
            }
            h1 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 30px 0 20px 0;
                padding: 20px;
                background: #2c3e50;
                color: white;
                border-radius: 8px;
                font-size: 1.8em;
            }
            h2 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 20px 0 15px 0;
                padding: 15px;
                background: #34495e;
                color: white;
                border-radius: 8px;
                font-size: 1.4em;
            }
            h3 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 15px 0 10px 0;
                padding: 12px;
                background: #7f8c8d;
                color: white;
                border-radius: 6px;
                font-size: 1.2em;
            }
            h4 {
                grid-column: 1 / -1;
                text-align: left;
                margin: 10px 0 8px 20px;
                padding: 8px 15px;
                background: #95a5a6;
                color: white;
                border-radius: 4px;
                font-size: 1.0em;
            }
            .toggle-controls-btn {
                position: absolute;
                right: 20px;
                top: 50%;
                transform: translateY(-50%);
                background: #ecf0f1;
                color: #2c3e50;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.8em;
                font-weight: normal;
            }
            .toggle-controls-btn:hover {
                background: #bdc3c7;
            }
            .control-curve.hidden {
                display: none;
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
        </style>
        <script>
            const Y_PADDING_RATIO = 0.06;

            function parseReadings(polyline) {
                const data = polyline.dataset.readings;
                if (!data) {
                    return [];
                }
                return data.split(',')
                    .map(Number)
                    .filter(value => Number.isFinite(value));
            }

            function getPlotConfig(svg) {
                const width = parseFloat(svg.getAttribute('width')) || 0;
                const height = parseFloat(svg.getAttribute('height')) || 0;
                const margin = parseFloat(svg.dataset.margin || 30);
                return {
                    margin,
                    plotWidth: Math.max(width - (2 * margin), 1),
                    plotHeight: Math.max(height - (2 * margin), 1)
                };
            }

            function buildPolylinePoints(readings, config, minValue, maxValue) {
                if (readings.length < 2) {
                    return '';
                }

                const denominator = Math.max(readings.length - 1, 1);
                const range = maxValue - minValue;
                const safeRange = range === 0 ? 1 : range;

                return readings.map((reading, index) => {
                    const x = config.margin + (index * config.plotWidth / denominator);
                    const normalized = (reading - minValue) / safeRange;
                    const y = config.margin + config.plotHeight - (config.plotHeight * normalized);
                    return `${x.toFixed(1)},${y.toFixed(1)}`;
                }).join(' ');
            }

            function computeScaleValues(polylines) {
                let allValues = [];
                polylines.forEach(polyline => {
                    allValues = allValues.concat(parseReadings(polyline));
                });

                if (allValues.length === 0) {
                    return null;
                }

                let minValue = Math.min(...allValues);
                let maxValue = Math.max(...allValues);
                let range = maxValue - minValue;

                if (range === 0) {
                    const adjustment = Math.max(Math.abs(maxValue) * 0.05, 1);
                    minValue -= adjustment;
                    maxValue += adjustment;
                    range = maxValue - minValue;
                }

                const padding = range * Y_PADDING_RATIO;
                return {
                    min: minValue - padding,
                    max: maxValue + padding
                };
            }

            function rescaleGraph(svg, includeControls) {
                if (!svg) {
                    return;
                }

                const mainCurves = Array.from(svg.querySelectorAll('.main-curve'));
                if (mainCurves.length === 0) {
                    return;
                }

                const curvesForScale = [...mainCurves];
                if (includeControls) {
                    curvesForScale.push(...svg.querySelectorAll('.control-curve'));
                }

                const scaleValues = computeScaleValues(curvesForScale);
                if (!scaleValues) {
                    return;
                }

                const config = getPlotConfig(svg);
                const allCurves = svg.querySelectorAll('.main-curve, .control-curve');

                allCurves.forEach(curve => {
                    const readings = parseReadings(curve);
                    if (readings.length < 2) {
                        return;
                    }
                    const points = buildPolylinePoints(readings, config, scaleValues.min, scaleValues.max);
                    if (points) {
                        curve.setAttribute('points', points);
                    }
                });

                const maxLabel = svg.querySelector('.y-axis-max');
                if (maxLabel) {
                    maxLabel.textContent = scaleValues.max.toFixed(0);
                }
                const minLabel = svg.querySelector('.y-axis-min');
                if (minLabel) {
                    minLabel.textContent = scaleValues.min.toFixed(0);
                }
            }

            function toggleControls(sectionId, scaleYAxis = true) {
                const section = document.getElementById(sectionId);
                if (!section) {
                    console.error('Section not found:', sectionId);
                    return;
                }

                // Get all control curves in this section
                const curves = section.querySelectorAll('.control-curve');
                const legends = section.querySelectorAll('.graph-legend');
                const svgs = section.querySelectorAll('svg');

                // Find the button - it's in the previous h4 sibling
                const h4 = section.previousElementSibling;
                const btn = h4 ? h4.querySelector('.toggle-controls-btn') : null;

                const isHidden = curves.length > 0 && curves[0].classList.contains('hidden');

                curves.forEach(curve => {
                    if (isHidden) {
                        curve.classList.remove('hidden');
                    } else {
                        curve.classList.add('hidden');
                    }
                });

                legends.forEach(legend => {
                    legend.style.display = isHidden ? 'block' : 'none';
                });

                // Determine target scaling (include controls when showing)
                const includeControls = isHidden;

                // Rescale Y-axis if enabled
                if (scaleYAxis) {
                    svgs.forEach(svg => {
                        rescaleGraph(svg, includeControls);
                    });
                }

                if (btn) {
                    btn.textContent = isHidden ? 'Hide Controls' : 'Show Controls';
                }
            }
        </script>
    </head>
    <body>
        <script>
            // Global setting for y-axis scaling
            const SCALE_Y_AXIS_ON_TOGGLE = {scale_y_axis_flag};
        </script>
        <div class="header">
            <h1>Sample Details Report</h1>
            <p style="color: #666;">All targets (including IC) with Azure (DXAI) and Machine (Embed) classifications</p>
            <p style="color: #999; font-size: 0.9em;">Control curves: <span style="color:#3498db;">━━ Positive</span> | <span style="color:#95a5a6;">··· Negative</span></p>
        </div>
        <div class="container">
    '''

    # Track current grouping
    current_sample = None
    current_mix = None
    current_mixtarget = None
    section_counter = 0

    # Classification labels
    cls_labels = {
        0: 'NEG',
        1: 'POS',
        2: 'EQUIV'
    }

    print(f"Generating sample details report for {len(records)} records...")

    current_file = None
    for record in tqdm(records, desc="Processing records"):
        rec_id, sample, file, mix, mixtarget, target, azure_cls, azure_cfd, embed_cls, embed_ct, source_table = record

        # Add Sample header (h2) when sample changes
        if sample != current_sample:
            html_content += f'''
            <h2>Sample: {sample}</h2>
            '''
            current_sample = sample
            current_file = None
            current_mix = None
            current_mixtarget = None

        # Add File/Run header (h3) when file changes (for duplicate runs)
        if file != current_file:
            html_content += f'''
            <h3>Run: {file}</h3>
            '''
            current_file = file
            current_mix = None
            current_mixtarget = None

        # Add Mix header (h3) when it changes
        if mix != current_mix:
            html_content += f'''
            <h3>Mix: {mix}</h3>
            '''
            current_mix = mix
            current_mixtarget = None

        # Add MixTarget header (h4) when it changes
        if mixtarget != current_mixtarget:
            section_counter += 1
            section_id = f'section_{section_counter}'
            html_content += f'''
            <h4 style="position: relative;">
                Target: {mixtarget}
                <button class="toggle-controls-btn" onclick="toggleControls('{section_id}', SCALE_Y_AXIS_ON_TOGGLE)">Show Controls</button>
            </h4>
            <div id="{section_id}" style="display: contents;">
            '''
            current_mixtarget = mixtarget

        # Get readings and generate graph
        try:
            readings = get_readings_for_id(conn, rec_id, source_table)
            if readings:
                # Get control curves - generic controls for this mix/target (not file-specific)
                cursor = conn.cursor()
                readings_columns = [f"readings{i}" for i in range(44)]
                readings_select = ", ".join(readings_columns)

                # Positive controls
                pos_controls = []
                cursor.execute(f"""
                    SELECT Sample, {readings_select}
                    FROM test_data
                    WHERE Mix = ? AND MixTarget = ? AND (UPPER(Sample) LIKE 'POS%')
                    AND in_use = 1
                    LIMIT 3
                """, (mix, mixtarget))
                for row in cursor.fetchall():
                    sample_name = row[0]
                    ctrl_readings = [r for r in row[1:] if r is not None]
                    if ctrl_readings:
                        pos_controls.append((sample_name, ctrl_readings))
                pos_controls = pos_controls if pos_controls else None

                # Negative controls
                neg_controls = []
                cursor.execute(f"""
                    SELECT Sample, {readings_select}
                    FROM test_data
                    WHERE Mix = ? AND MixTarget = ? AND (UPPER(Sample) LIKE 'NTC%' OR UPPER(Sample) LIKE 'NPC%' OR UPPER(Sample) LIKE 'NEG%')
                    AND in_use = 1
                    LIMIT 3
                """, (mix, mixtarget))
                for row in cursor.fetchall():
                    sample_name = row[0]
                    ctrl_readings = [r for r in row[1:] if r is not None]
                    if ctrl_readings:
                        neg_controls.append((sample_name, ctrl_readings))
                neg_controls = neg_controls if neg_controls else None

                # Format result labels
                azure_label = cls_labels.get(azure_cls, 'N/A') if azure_cls is not None else 'N/A'
                embed_label = cls_labels.get(embed_cls, 'N/A') if embed_cls is not None else 'N/A'
                embed_ct_str = f"({embed_ct:.2f})" if embed_ct is not None else ""

                # Enhanced metadata with both results in header
                metadata = {
                    'AzureCls': azure_cls,
                    'AzureCFD': azure_cfd,
                    'EmbedCls': embed_cls,
                    'EmbedCt': embed_ct,
                    'Sample': sample,
                    'File': file,
                    'Tube': mixtarget,
                    'Target': target
                }

                svg_graph = generate_svg_graph(rec_id, readings, metadata, show_cfd=show_cfd,
                                              pos_controls=pos_controls,
                                              neg_controls=neg_controls,
                                              show_machine_result=False)

                # Modify SVG graph header to include results instead of separate div
                # Find and replace the graph-header to include results
                graph_header = f"{sample} | {file[:12]}... | {mixtarget}"
                result_label = f" | Azure: {azure_label} | Embed: {embed_label}{' '+embed_ct_str if embed_ct_str else ''}"

                svg_graph = svg_graph.replace(
                    f'<div class="graph-header">\n            {graph_header}\n        </div>',
                    f'<div class="graph-header">\n            {graph_header}{result_label}\n        </div>'
                )

                html_content += svg_graph

        except Exception as e:
            print(f"Error processing record {rec_id} from {source_table}: {e}")
            continue

    # Close last section div
    html_content += '</div>\n'

    # Close HTML
    html_content += '''
        </div>
    </body>
    </html>
    '''

    # Replace flag placeholder with actual value
    scale_y_axis_str = 'true' if scale_y_axis else 'false'
    html_content = html_content.replace('{scale_y_axis_flag}', scale_y_axis_str)

    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"\nHTML report generated: {output_file}")
    print(f"Total records: {len(records)}")


def generate_html_report(conn, records, output_file, show_cfd=False, compare_embed=False, scale_y_axis=True):
    """
    Generate HTML report organized by Mix, MixTarget, and classification.

    Args:
        conn: Database connection
        records: List of records to process
        output_file: Output HTML file path
        show_cfd: Show confidence values
        compare_embed: If True, group by comparison categories (DISCREPANT/EQUIVOCAL/AGREED)
                      instead of just AzureCls
        scale_y_axis: Rescale y-axis when toggling controls (default: True)
    """

    html_content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Azure Classification Report</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 10px;
                background-color: #f5f5f5;
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
            }
            .header {
                text-align: center;
                margin: 20px 0;
            }
            h1 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 30px 0 20px 0;
                padding: 20px;
                background: #2c3e50;
                color: white;
                border-radius: 8px;
                font-size: 1.8em;
                position: relative;
                cursor: pointer;
                user-select: none;
            }
            h1:hover {
                background: #34495e;
            }
            h1::after {
                content: '▼';
                position: absolute;
                right: 30px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 0.6em;
            }
            h1.collapsed::after {
                content: '▶';
            }
            h1.report-title {
                cursor: default;
            }
            h1.report-title:hover {
                background: #2c3e50;
            }
            h1.report-title::after {
                content: '';
            }
            h2 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 30px 0 15px 0;
                padding: 15px;
                background: #34495e;
                color: white;
                border-radius: 8px;
                font-size: 1.4em;
            }
            h3 {
                grid-column: 1 / -1;
                text-align: center;
                margin: 20px 0 10px 0;
                padding: 12px;
                background: #7f8c8d;
                color: white;
                border-radius: 6px;
                font-size: 1.2em;
                position: relative;
            }
            h4 {
                grid-column: 1 / -1;
                text-align: left;
                margin: 15px 0 8px 20px;
                padding: 8px 15px;
                background: #95a5a6;
                color: white;
                border-radius: 4px;
                font-size: 1.0em;
            }
            .toggle-controls-btn {
                position: absolute;
                right: 20px;
                top: 50%;
                transform: translateY(-50%);
                background: #ecf0f1;
                color: #2c3e50;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.8em;
                font-weight: normal;
            }
            .toggle-controls-btn:hover {
                background: #bdc3c7;
            }
            .control-curve.hidden {
                display: none;
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
        </style>
        <script>
            const Y_PADDING_RATIO = 0.06;

            function parseReadings(polyline) {
                const data = polyline.dataset.readings;
                if (!data) {
                    return [];
                }
                return data.split(',')
                    .map(Number)
                    .filter(value => Number.isFinite(value));
            }

            function getPlotConfig(svg) {
                const width = parseFloat(svg.getAttribute('width')) || 0;
                const height = parseFloat(svg.getAttribute('height')) || 0;
                const margin = parseFloat(svg.dataset.margin || 30);
                return {
                    margin,
                    plotWidth: Math.max(width - (2 * margin), 1),
                    plotHeight: Math.max(height - (2 * margin), 1)
                };
            }

            function buildPolylinePoints(readings, config, minValue, maxValue) {
                if (readings.length < 2) {
                    return '';
                }

                const denominator = Math.max(readings.length - 1, 1);
                const range = maxValue - minValue;
                const safeRange = range === 0 ? 1 : range;

                return readings.map((reading, index) => {
                    const x = config.margin + (index * config.plotWidth / denominator);
                    const normalized = (reading - minValue) / safeRange;
                    const y = config.margin + config.plotHeight - (config.plotHeight * normalized);
                    return `${x.toFixed(1)},${y.toFixed(1)}`;
                }).join(' ');
            }

            function computeScaleValues(polylines) {
                let allValues = [];
                polylines.forEach(polyline => {
                    allValues = allValues.concat(parseReadings(polyline));
                });

                if (allValues.length === 0) {
                    return null;
                }

                let minValue = Math.min(...allValues);
                let maxValue = Math.max(...allValues);
                let range = maxValue - minValue;

                if (range === 0) {
                    const adjustment = Math.max(Math.abs(maxValue) * 0.05, 1);
                    minValue -= adjustment;
                    maxValue += adjustment;
                    range = maxValue - minValue;
                }

                const padding = range * Y_PADDING_RATIO;
                return {
                    min: minValue - padding,
                    max: maxValue + padding
                };
            }

            function rescaleGraph(svg, includeControls) {
                if (!svg) {
                    return;
                }

                const mainCurves = Array.from(svg.querySelectorAll('.main-curve'));
                if (mainCurves.length === 0) {
                    return;
                }

                const curvesForScale = [...mainCurves];
                if (includeControls) {
                    curvesForScale.push(...svg.querySelectorAll('.control-curve'));
                }

                const scaleValues = computeScaleValues(curvesForScale);
                if (!scaleValues) {
                    return;
                }

                const config = getPlotConfig(svg);
                const allCurves = svg.querySelectorAll('.main-curve, .control-curve');

                allCurves.forEach(curve => {
                    const readings = parseReadings(curve);
                    if (readings.length < 2) {
                        return;
                    }
                    const points = buildPolylinePoints(readings, config, scaleValues.min, scaleValues.max);
                    if (points) {
                        curve.setAttribute('points', points);
                    }
                });

                const maxLabel = svg.querySelector('.y-axis-max');
                if (maxLabel) {
                    maxLabel.textContent = scaleValues.max.toFixed(0);
                }
                const minLabel = svg.querySelector('.y-axis-min');
                if (minLabel) {
                    minLabel.textContent = scaleValues.min.toFixed(0);
                }
            }

            function toggleControls(sectionId, scaleYAxis = true) {
                const section = document.getElementById(sectionId);
                if (!section) {
                    console.error('Section not found:', sectionId);
                    return;
                }

                const curves = section.querySelectorAll('.control-curve');
                const legends = section.querySelectorAll('.graph-legend');
                const svgs = section.querySelectorAll('svg');
                const header = section.previousElementSibling;
                const btn = header ? header.querySelector('.toggle-controls-btn') : null;

                const isHidden = curves.length > 0 && curves[0].classList.contains('hidden');

                curves.forEach(curve => {
                    if (isHidden) {
                        curve.classList.remove('hidden');
                    } else {
                        curve.classList.add('hidden');
                    }
                });

                legends.forEach(legend => {
                    legend.style.display = isHidden ? 'block' : 'none';
                });

                const includeControls = isHidden;

                if (scaleYAxis) {
                    svgs.forEach(svg => {
                        rescaleGraph(svg, includeControls);
                    });
                }

                if (btn) {
                    btn.textContent = isHidden ? 'Hide Controls' : 'Show Controls';
                }
            }

            function toggleCategory(categoryId) {
                const section = document.getElementById(`section-${categoryId}`);
                const header = document.getElementById(`header-${categoryId}`);

                if (section.style.display === 'none') {
                    section.style.display = 'contents';
                    header.classList.remove('collapsed');
                } else {
                    section.style.display = 'none';
                    header.classList.add('collapsed');
                }
            }
        </script>
    </head>
    <body>
        <script>
            // Global setting for y-axis scaling
            const SCALE_Y_AXIS_ON_TOGGLE = {scale_y_axis_flag};
        </script>
        <div class="header">
            <h1 class="report-title">Azure Classification Report</h1>
            <p style="color: #666;">Original curves from readings + test_data tables, organized by Mix, Target, and Classification</p>
            <p style="color: #999; font-size: 0.9em;">Control curves: <span style="color:#3498db;">━━ Positive</span> | <span style="color:#95a5a6;">··· Negative</span></p>
        </div>
        <div class="container">
    '''

    # Track current grouping
    current_comparison_category = None  # Top level when compare_embed is True
    current_mix = None
    current_mixtarget = None
    current_azurecls = None
    section_counter = 0
    category_counter = 0  # For tracking comparison categories

    # Classification labels
    cls_labels = {
        0: 'NEGATIVE',
        1: 'POSITIVE',
        2: 'AMBIGUOUS'
    }

    # Comparison category labels
    comparison_labels = {
        'DISCREPANT': 'DISCREPANT RESULTS',
        'EQUIVOCAL': 'EQUIVOCAL RESULTS',
        'AGREED': 'AGREED RESULTS',
        'NO_EMBED': 'NO EMBED RESULT'
    }

    # Count statistics
    stats = {
        'total': 0,
        'by_mix': {},
        'by_cls': {0: 0, 1: 0, 2: 0},
        'by_table': {'readings': 0, 'test_data': 0},
        'by_comparison': {'DISCREPANT': 0, 'EQUIVOCAL': 0, 'AGREED': 0, 'NO_EMBED': 0}
    }

    # Cache for positive control samples per mix-target
    pos_control_cache = {}

    print(f"Generating HTML report for {len(records)} records...")

    for record in tqdm(records, desc="Processing records"):
        record_id, mix, mixtarget, target, azure_cls, azure_cfd, sample, file, file_uid, tube, embed_cls, embed_ct, source_table = record

        stats['total'] += 1
        stats['by_cls'][azure_cls] = stats['by_cls'].get(azure_cls, 0) + 1
        stats['by_mix'][mix] = stats['by_mix'].get(mix, 0) + 1
        stats['by_table'][source_table] += 1

        # Calculate comparison category if compare_embed mode is enabled
        comparison_category = None
        if compare_embed:
            comparison_category = classify_comparison(azure_cls, embed_cls)
            stats['by_comparison'][comparison_category] += 1
            # Skip NO_EMBED records if there are none to show
            if comparison_category == 'NO_EMBED' and stats['by_comparison']['NO_EMBED'] == 1:
                # We'll handle this at the end - for now just track it
                pass

        if compare_embed:
            # When compare_embed is enabled: Comparison Category → Mix → MixTarget → AzureCls

            # Add Comparison Category header (h1) when it changes
            if comparison_category != current_comparison_category:
                # Close previous category section div if exists
                if current_comparison_category is not None:
                    html_content += '</div>\n'  # Close previous category-section

                # Skip NO_EMBED if empty (don't show header)
                if comparison_category == 'NO_EMBED':
                    current_comparison_category = comparison_category
                    continue

                category_counter += 1
                comp_label = comparison_labels.get(comparison_category, comparison_category)

                # Hide AGREED (3rd category) and beyond by default
                if category_counter >= 3:
                    section_style = 'display: none;'
                    header_class = ' collapsed'
                else:
                    section_style = 'display: contents;'
                    header_class = ''

                html_content += f'''
            <h1 id="header-cat{category_counter}" class="{header_class}" onclick="toggleCategory('cat{category_counter}')">{comp_label}</h1>
            <div id="section-cat{category_counter}" style="{section_style}">
            '''
                current_comparison_category = comparison_category
                current_mix = None  # Reset Mix
                current_mixtarget = None  # Reset MixTarget
                current_azurecls = None  # Reset AzureCls

            # Add Mix header (h2) when it changes
            if mix != current_mix:
                html_content += f'''
            <h2>Mix: {mix}</h2>
            '''
                current_mix = mix
                current_mixtarget = None  # Reset MixTarget
                current_azurecls = None  # Reset AzureCls

            # Add MixTarget header (h3) when it changes
            if mixtarget != current_mixtarget:
                # Close previous section div if exists
                if current_azurecls is not None:
                    html_content += '</div>\n'
                    current_azurecls = None

                section_counter += 1
                section_id = f'section_{section_counter}'
                html_content += f'''
            <h3>
                Target: {mixtarget}
                <button class="toggle-controls-btn" onclick="toggleControls('{section_id}', SCALE_Y_AXIS_ON_TOGGLE)">Hide Controls</button>
            </h3>
            <div id="{section_id}" style="display: contents;">
            '''
                current_mixtarget = mixtarget
                current_azurecls = None  # Reset AzureCls

            # Add AzureCls sub-header (h4) when it changes
            if azure_cls != current_azurecls:
                cls_label = cls_labels.get(azure_cls, f'Class {azure_cls}')
                html_content += f'''
                <h4 style="grid-column: 1 / -1; text-align: left; margin: 15px 0 8px 20px; padding: 8px 15px; background: #95a5a6; color: white; border-radius: 4px; font-size: 1.0em;">
                    {cls_label}
                </h4>
                '''
                current_azurecls = azure_cls
        else:
            # Original behavior: Mix → MixTarget → AzureCls

            # Add Mix header (h1) when it changes
            if mix != current_mix:
                html_content += f'''
            <h1>Mix: {mix}</h1>
            '''
                current_mix = mix
                current_mixtarget = None  # Reset MixTarget
                current_azurecls = None  # Reset AzureCls

            # Add MixTarget header (h2) when it changes
            if mixtarget != current_mixtarget:
                html_content += f'''
            <h2>Target: {mixtarget}</h2>
            '''
                current_mixtarget = mixtarget
                current_azurecls = None  # Reset AzureCls

            # Add AzureCls header (h3) when it changes
            if azure_cls != current_azurecls:
                # Close previous section div if exists
                if current_azurecls is not None:
                    html_content += '</div>\n'

                section_counter += 1
                section_id = f'section_{section_counter}'
                cls_label = cls_labels.get(azure_cls, f'Class {azure_cls}')
                html_content += f'''
            <h3>
                {cls_label}
                <button class="toggle-controls-btn" onclick="toggleControls('{section_id}', SCALE_Y_AXIS_ON_TOGGLE)">Hide Controls</button>
            </h3>
            <div id="{section_id}" style="display: contents;">
            '''
                current_azurecls = azure_cls

        # Get readings and generate graph
        try:
            readings = get_readings_for_id(conn, record_id, source_table)
            if readings:
                # Get control curves for this sample
                # Cache positive control samples lookup (use MixTarget, not Target wavelength)
                cache_key = f"{mix}_{mixtarget}"
                if cache_key not in pos_control_cache:
                    pos_control_cache[cache_key] = get_positive_control_samples(conn, mix, mixtarget)

                pos_control_samples = pos_control_cache[cache_key]

                # Fetch positive controls
                pos_controls = []
                if pos_control_samples and file_uid:
                    pos_control_records = get_control_curves(conn, file_uid, mix, mixtarget, pos_control_samples, is_positive=True)
                    pos_controls = [(sample_name, readings) for _, sample_name, readings, _ in pos_control_records]

                # Fetch negative controls
                neg_controls = []
                if file_uid:
                    neg_control_records = get_control_curves(conn, file_uid, mix, mixtarget, None, is_positive=False)
                    neg_controls = [(sample_name, readings) for _, sample_name, readings, _ in neg_control_records]

                metadata = {
                    'AzureCls': azure_cls,
                    'AzureCFD': azure_cfd,
                    'Sample': sample,
                    'File': file,
                    'Tube': tube,
                    'EmbedCls': embed_cls,
                    'EmbedCt': embed_ct
                }
                svg_graph = generate_svg_graph(record_id, readings, metadata, show_cfd=show_cfd,
                                              pos_controls=pos_controls if pos_controls else None,
                                              neg_controls=neg_controls if neg_controls else None,
                                              show_machine_result=compare_embed)
                html_content += svg_graph
        except Exception as e:
            print(f"Error processing record {record_id} from {source_table}: {e}")
            continue

    # Close last section div
    if current_azurecls is not None:
        html_content += '</div>\n'  # Close target section

    # Close last category section div
    if compare_embed and current_comparison_category is not None:
        html_content += '</div>\n'  # Close category-section

    # Build statistics HTML
    stats_comparison_html = ''
    if compare_embed:
        stats_comparison_html = f'''
            <p><strong>By Comparison:</strong>
               Discrepant: {stats['by_comparison']['DISCREPANT']} |
               Equivocal: {stats['by_comparison']['EQUIVOCAL']} |
               Agreed: {stats['by_comparison']['AGREED']}'''
        if stats['by_comparison']['NO_EMBED'] > 0:
            stats_comparison_html += f''' |
               No Embed: {stats['by_comparison']['NO_EMBED']}'''
        stats_comparison_html += '\n            </p>'

    # Close HTML
    html_content += f'''
        </div>
        <div class="stats">
            <h3>Report Statistics</h3>
            <p><strong>Total Records:</strong> {stats['total']}</p>
            <p><strong>By Source Table:</strong>
               readings: {stats['by_table']['readings']} |
               test_data: {stats['by_table']['test_data']}
            </p>
            <p><strong>By Classification:</strong>
               Positive: {stats['by_cls'].get(1, 0)} |
               Negative: {stats['by_cls'].get(0, 0)} |
               Ambiguous: {stats['by_cls'].get(2, 0)}
            </p>
            {stats_comparison_html}
            <p><strong>By Mix:</strong> {' | '.join([f'{k}: {v}' for k, v in sorted(stats['by_mix'].items())])}</p>
        </div>
    </body>
    </html>
    '''

    # Replace flag placeholder with actual value
    scale_y_axis_str = 'true' if scale_y_axis else 'false'
    html_content = html_content.replace('{scale_y_axis_flag}', scale_y_axis_str)

    # Write file
    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"\nHTML report generated: {output_file}")
    print(f"Total records: {stats['total']}")
    print(f"  readings: {stats['by_table']['readings']}, test_data: {stats['by_table']['test_data']}")
    print(f"Positive: {stats['by_cls'].get(1, 0)}, Negative: {stats['by_cls'].get(0, 0)}, Ambiguous: {stats['by_cls'].get(2, 0)}")
    if compare_embed:
        print(f"Comparison: Discrepant: {stats['by_comparison']['DISCREPANT']}, Equivocal: {stats['by_comparison']['EQUIVOCAL']}, Agreed: {stats['by_comparison']['AGREED']}, No Embed: {stats['by_comparison']['NO_EMBED']}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate HTML report of Azure classification results from readings + test_data tables'
    )
    parser.add_argument('--db', default='readings.db',
                       help='Path to SQLite database file (default: readings.db)')
    parser.add_argument('--output', default='output_data/azure_report.html',
                       help='Output HTML file path (default: output_data/azure_report.html)')
    parser.add_argument('--show-cfd', action='store_true',
                       help='Show AzureCFD (confidence) values in top-right of each graph (default: off)')
    parser.add_argument('--include-ic', action='store_true',
                       help='Include IC (internal control) targets in the report (default: excluded)')
    parser.add_argument('--compare-embed', action='store_true',
                       help='Group results by comparison between Azure and embedded machine classifications (DISCREPANT/EQUIVOCAL/AGREED)')
    parser.add_argument('--sample-details', nargs='+', type=int,
                       help='Generate sample details report for specific sample IDs (shows all targets including IC, with both Azure and Embed results)')
    parser.add_argument('--dont-scale-y', action='store_true',
                       help='Disable y-axis rescaling when toggling controls (default: y-axis rescales to fit visible data)')

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db).exists():
        print(f"Error: Database file not found: {args.db}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(args.db)

    # Sample details mode
    if args.sample_details:
        print(f"Reading records for samples: {args.sample_details}...")
        records = get_sample_detail_records(conn, args.sample_details)

        if not records:
            print(f"No records found for samples: {args.sample_details}")
            conn.close()
            sys.exit(1)

        print(f"Found {len(records)} records for {len(args.sample_details)} samples")

        # Generate sample details report
        scale_y_axis = not args.dont_scale_y
        generate_sample_details_report(conn, records, args.output, show_cfd=args.show_cfd, scale_y_axis=scale_y_axis)
    else:
        # Standard comparison mode
        filter_msg = "" if args.include_ic else " (excluding IC targets)"
        print(f"Reading Azure classification records from both readings and test_data tables{filter_msg}...")
        records = get_azure_records(conn, include_ic=args.include_ic, compare_embed=args.compare_embed)

        if not records:
            print(f"No records with Azure classification found in database")
            conn.close()
            sys.exit(1)

        print(f"Found {len(records)} records with Azure classification")

        # Generate HTML report
        scale_y_axis = not args.dont_scale_y
        generate_html_report(conn, records, args.output, show_cfd=args.show_cfd, compare_embed=args.compare_embed, scale_y_axis=scale_y_axis)

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
