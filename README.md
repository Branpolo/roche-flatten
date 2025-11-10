# Roche Flatten - CUSUM Analysis and Curve Flattening

Time series analysis tools using CUSUM (Cumulative Sum) algorithms and curve flattening for PCR laboratory data processing.

## Overview

The pipeline processes laboratory reading data through several stages:
1. **CUSUM Analysis**: Detect downward trends in time series data
2. **Curve Flattening**: Modify readings to remove detected downward slopes
3. **Database Storage**: Store results in SQLite database with flattened readings
4. **Visualization**: Generate HTML reports for analysis and validation
5. **PCRAI Export**: Generate PCRAI files for downstream platforms

## Core Scripts

### 1. `apply_corrected_cusum_all.py`
**Purpose**: Calculate CUSUM values for all records and update database

**Algorithm**:
- Converts readings to SVG coordinates (0-400 pixel range)
- Applies simple inversion: `max(y_vals) - y_vals`
- Smooths data with 5-point rolling window
- Computes negative CUSUM to detect downward trends

**Usage**:
```bash
python3 flatten/apply_corrected_cusum_all.py
```

**Output**: Updates `readings` table with `cusum0`-`cusum43` and `cusum_min_correct` columns

---

### 2. `create_flattened_database_fast.py`
**Purpose**: Create flattened version of curves with significant downward trends

**Logic**:
- Creates `flatten` table (copy of `readings` table)
- Identifies curves with CUSUM min ≤ -80 (configurable threshold)
- Flattens readings before CUSUM minimum point to target value + noise
- Processes ~10,534 records efficiently using batch operations

**Usage**:
```bash
python3 flatten/create_flattened_database_fast.py

# With sanity check to prevent flattening shallow dips
python3 flatten/create_flattened_database_fast.py --sanity-check-slope --threshold -100
```

**Output**: Creates `flatten` table with modified readings for detected downward trends

---

### 3. `generate_flattened_cusum_html.py` ⭐
**Purpose**: Generate HTML visualizations with configurable CUSUM parameters

**Parameters**:
- `--k [number]`: CUSUM tolerance parameter (default: 0.0, suggested: 0.1-0.3)
- `--ids [id1,id2,...]`: Process specific record IDs
- `--example-dataset`: Use curated example dataset from feedback plots
- `--limit [n]`: Limit number of curves to process
- `--threshold [n]`: CUSUM threshold for flattening (default: -80)
- `--sanity-check-slope`: Enable sanity check to verify CUSUM min represents actual decrease
- `--sanity-lob`: Use Line of Best Fit gradient check instead of average comparison

**Usage Examples**:
```bash
# Test different k values on example dataset
python3 flatten/generate_flattened_cusum_html.py --example-dataset --k 0.2 --limit 20

# Analyze specific problematic cases
python3 flatten/generate_flattened_cusum_html.py --ids 2112,403,418 --k 0.1

# Generate full analysis with custom parameters
python3 flatten/generate_flattened_cusum_html.py --k 0.15 --threshold -100 --limit 500

# Enable sanity check to prevent flattening of shallow dips
python3 flatten/generate_flattened_cusum_html.py --example-dataset --sanity-check-slope --threshold -50

# Show only records that failed sanity check
python3 flatten/generate_flattened_cusum_html.py --sanity-check-slope --only-failed sanity --all

# Use Line of Best Fit gradient check
python3 flatten/generate_flattened_cusum_html.py --sanity-lob --example-dataset --threshold -50
```

**Output**: HTML files in `output_data/` with interactive graphs showing original (blue), flattened (green), and CUSUM (red dashed) curves

---

### 4. `generate_database_flattened_html_fixed.py`
**Purpose**: Visualize actual flattened curves stored in database

**Features**:
- Reads flattened readings from `flatten` table
- Shows verification of flattening process
- Handles CUSUM alignment issues (Results column offset)
- Generates sample and full HTML reports

**Usage**:
```bash
python3 flatten/generate_database_flattened_html_fixed.py
```

**Output**: HTML files showing database-stored flattened curves with original CUSUM overlays

---

### 5. `manage_example_ids.py` 🆕
**Purpose**: Manage the example IDs dataset used for testing and validation

**Parameters**:
- `--add [id1,id2,...]`: Add IDs to the example dataset
- `--remove [id1,id2,...]`: Remove IDs from the example dataset
- `--list`: List all current example IDs (default action)
- `--validate`: Check if IDs exist in readings table before adding
- `--db [path]`: Path to database file (default: ~/dbs/readings.db)

**Usage Examples**:
```bash
# List current example IDs
python3 flatten/manage_example_ids.py --list

# Add new IDs to example dataset
python3 flatten/manage_example_ids.py --add 500,600,700

# Remove IDs from example dataset
python3 flatten/manage_example_ids.py --remove 500,600
```

**Output**: Console output showing added/removed/listed IDs

---

### 6. `generate_pcrai_from_db.py`
**Purpose**: Export database records to PCRAI format for downstream platforms

**Parameters**:
- `--all`: Generate PCRAI for all unique filenames in database
- `--files [file1,file2,...]`: Generate PCRAI for specific files
- `--db [path]`: Custom database path (default: ~/dbs/readings.db)
- `--output [dir]`: Output directory (default: output_data)

**Usage Examples**:
```bash
# Generate all PCRAI files
python3 flatten/generate_pcrai_from_db.py --all

# Generate specific files
python3 flatten/generate_pcrai_from_db.py --files exp4E042354,exp4T170243

# Custom output location
python3 flatten/generate_pcrai_from_db.py --all --output /path/to/pcrai/files
```

**Features**:
- Dynamic mix detection per file (no hardcoded assumptions)
- Uses improved target names from database (CMV, HSV1, etc.)
- Exports flattened readings for enhanced analysis
- Comprehensive validation and error handling
- Processes 100+ files generating ~174MB of PCRAI data

**Output**: `.pcrai` files (JSON format) ready for next platform

---

### 7. `compare_k_parameters.py` ⭐
**Purpose**: Compare different k tolerance values and identify curves where flattening decision changes

**Parameters**:
- `--default-k [number]`: Default CUSUM tolerance parameter (default: 0.0)
- `--test-k [number]`: Test CUSUM tolerance parameter to compare
- `--use-default-derivative`: Use derivative analysis for default comparison
- `--use-test-derivative`: Use derivative analysis for test comparison
- `--derivative-threshold [number]`: Threshold for derivative-based flattening
- `--cusum-limit [number]`: CUSUM threshold for flattening (default: -80)
- `--ids [id1,id2,...]`: Process specific record IDs
- `--example-dataset`: Use curated example dataset
- `--limit [n]`: Limit number of curves to process

**Features**:
- **Dual Method Support**: Compare CUSUM vs CUSUM or CUSUM vs derivative
- **Derivative Analysis**: Calculates rate of change between consecutive readings
- **Change Detection**: Only shows curves where flattening decision changes
- **Database Integration**: Uses k=0.0 database values for accuracy
- **Visual Comparison**: Clear side-by-side analysis value display
- **Color-coded Status**: Red for lost flattening, green for gained flattening

**Usage Examples**:
```bash
# Compare k=0.0 vs k=0.2 with threshold -80
python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=0.2 --cusum-limit=-80

# Use example dataset with larger k difference
python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=1.0 --cusum-limit=-150 --example-dataset

# Test specific IDs near threshold boundary
python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=3.0 --cusum-limit=-150 --ids=454,1401,1457

# Compare CUSUM k=0.0 with derivative analysis
python3 flatten/compare_k_parameters.py --use-test-derivative --derivative-threshold=-0.2 --ids=2112,1256,1264

# With sanity check to prevent false positives
python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=0.2 --sanity-check-slope --example-dataset
```

**Output**: HTML files in `output_data/` showing only curves where flattening decision changes

---

### 8. `generate_azure_report.py` ⭐
**Purpose**: Generate HTML reports with Azure classification results and optional control curves

**Parameters**:
- `--db [path]`: Path to SQLite database file (default: readings.db)
- `--output [path]`: Output HTML file path (default: output_data/azure_report.html)
- `--sample-details [id1,id2,...]`: Generate report for specific sample IDs (shows all targets)
- `--show-cfd`: Display Azure confidence values in top-right corner of graphs
- `--include-ic`: Include IC (internal control) targets (default: excluded)
- `--compare-embed`: Group results by comparison between Azure and embedded machine classifications
- `--dont-scale-y`: Disable y-axis rescaling when toggling control curves (default: enabled)

**Features**:
- **Control Curves**: Optional positive/negative control curves with toggle visibility
- **Smart Y-axis Scaling**: Automatically rescales to fit all visible data when controls are shown
- **Azure Classification**: Color-coded curves by classification (green=negative, red=positive, orange=ambiguous)
- **Embedded Results**: Optional display of machine learning classification results
- **Sample Organization**: Organized by Sample → Run → Mix → Target

**Usage Examples**:
```bash
# Standard Azure report
python3 flatten/generate_azure_report.py --db ~/dbs/readings.db --output output_data/azure_report.html

# Generate report for specific samples
python3 flatten/generate_azure_report.py --db ~/dbs/readings.db --sample-details 1536470 1536107 1536068 --output output_data/custom_samples.html

# Show confidence values
python3 flatten/generate_azure_report.py --show-cfd --output output_data/azure_report_with_cfd.html

# Include IC targets
python3 flatten/generate_azure_report.py --include-ic --output output_data/azure_report_full.html

# Compare with embedded machine results (group by DISCREPANT/EQUIVOCAL/AGREED)
python3 flatten/generate_azure_report.py --compare-embed --output output_data/azure_embed_comparison.html

# Disable y-axis rescaling (keep fixed scale)
python3 flatten/generate_azure_report.py --dont-scale-y --output output_data/azure_report_fixed_scale.html
```

**Output**: Interactive HTML report with graphs and optional control curves
- Main sample curve displayed at appropriate scale
- Control curves initially hidden with "Show Controls" button
- Y-axis automatically rescales when toggling control visibility
- Y-axis returns to normal scale when controls are hidden again

**Features**:
- **Interactive Controls**: Toggle visibility of positive/negative control curves
- **Smart Scaling**: Y-axis rescales to fit visible curves when controls are shown
- **Color Legend**: Positive controls (blue dashed), Negative controls (gray dotted)
- **Responsive Layout**: 5-column grid layout for easy browsing

## CUSUM Parameter Guidelines

### k Parameter Range
After data scaling analysis:
- **Original readings**: Vary by experiment (e.g., 6.55-7.32 for ID 2112)
- **After SVG scaling**: 0-400 pixel range (margin: 50-350)
- **After inversion**: 0-300 range, std dev ~102, mean ~127

**Recommended k values**: 0.1-0.3 (based on scaled data characteristics)
- **k=0.0**: Most sensitive, detects all changes
- **k=0.1**: Moderate tolerance, filters small fluctuations
- **k=0.3**: Higher tolerance, only significant trends

### Threshold Parameter
- **Default**: -80 (flattens ~10,534 of 19,120 curves)
- **Lower** (e.g., -100): More selective flattening
- **Higher** (e.g., -50): More aggressive flattening

## Database Schema

### Main Tables
- **`readings`**: Original data with CUSUM columns added
- **`flatten`**: Flattened curve data for significant downward trends
- **`example_ids`**: Curated test set (34 IDs) from feedback analysis

### Key Columns
- **`cusum0`-`cusum43`**: CUSUM values for each reading cycle
- **`cusum_min_correct`**: Minimum CUSUM value for trend detection
- **`in_use`**: Filter for active records (1=active, 0=filtered)

## Output Files

### HTML Visualizations
- `output_data/example_cusum_k[X].html`: Example dataset with k parameter X
- `output_data/all_cusum_k[X].html`: Full dataset analysis
- `output_data/custom_ids_cusum_k[X].html`: Specific ID analysis
- `output_data/k_comparison_[dataset]_k[X]_vs_k[Y]_lim[Z].html`: K parameter comparison results

### PCRAI Export Files
- `output_data/[filename].pcrai`: Laboratory data in PCRAI JSON format
- One file per unique filename in database
- Contains: metadata, mixes, wells, and 45-cycle fluorescence data

## Workflow Recommendations

1. **Parameter Testing**:
   ```bash
   python3 flatten/generate_flattened_cusum_html.py --example-dataset --k 0.1 --limit 10
   python3 flatten/generate_flattened_cusum_html.py --example-dataset --k 0.2 --limit 10
   python3 flatten/generate_flattened_cusum_html.py --example-dataset --k 0.3 --limit 10
   ```

2. **Validation**:
   ```bash
   python3 flatten/generate_flattened_cusum_html.py --ids 2112,403,418,423,424 --k 0.15
   ```

3. **K Parameter Comparison**:
   ```bash
   # Find curves that change flattening decision between k values
   python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=0.2 --cusum-limit=-80 --example-dataset

   # Test near threshold boundaries
   python3 flatten/compare_k_parameters.py --default-k=0.0 --test-k=1.0 --cusum-limit=-150 --limit=100
   ```

4. **Production**:
   ```bash
   # Update CUSUM with optimal k
   python3 flatten/apply_corrected_cusum_all.py --k 0.15

   # Regenerate flattened database
   python3 flatten/create_flattened_database_fast.py

   # Export PCRAI files
   python3 flatten/generate_pcrai_from_db.py --all
   ```

## Standardized Command Line Parameters

All Python scripts support a standardized set of command line parameters for consistent usage across the pipeline.

### Core Parameters

#### Data Source Parameters
- **`--db [path]`**: Path to SQLite database file (default: ~/dbs/readings.db)
- **`--output [directory]`**: Output directory for generated files (default: output_data)

#### Record Selection Parameters
- **`--ids [id1,id2,...]`**: Comma-separated list of specific record IDs to process
- **`--example-dataset`**: Use curated example dataset (34 IDs)
- **`--all`**: Process all records in database
- **`--limit [n]`**: Limit number of records to process

#### CUSUM Algorithm Parameters
- **`--k [number]`**: CUSUM tolerance parameter (default: 0.0, recommended: 0.1-0.3)
- **`--default-k [number]`**: Default CUSUM tolerance for comparisons
- **`--test-k [number]`**: Test CUSUM tolerance for comparison

#### Threshold Parameters
- **`--threshold [number]`**: CUSUM threshold for flattening decision (default: -80)
- **`--cusum-limit [number]`**: Alias for `--threshold`
- **`--sanity-check-slope`**: Enable sanity check to verify CUSUM min represents actual decrease
- **`--sanity-lob`**: Use Line of Best Fit gradient check
- **`--only-failed [type]`**: Filter to show only specific failure cases (threshold, sanity, sanity-lob, changes)

#### Sorting and Display Parameters
- **`--sort-order [up|down]`**: Sort order for results (up=low to high, down=high to low)
- **`--sort-by [cusum|id|db-cusum]`**: Sort criteria for results

#### File-specific Parameters (PCRAI Generation)
- **`--files [file1,file2,...]`**: Comma-separated list of filenames to process

### Parameter Compatibility Matrix

| Script | --all | --files | --db | --output | --k | --default-k | --test-k | --threshold | --ids | --example-dataset | --limit | --sort-order | --sort-by | --sanity-check-slope | --sanity-lob | --sample-details |
|--------|-------|---------|------|----------|-----|-------------|----------|-------------|-------|-------------------|---------|--------------|-----------|---------------------|--------------|------------------|
| `apply_corrected_cusum_all.py` | ❌* | ❌* | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `create_flattened_database_fast.py` | ❌* | ❌* | ✅ | ❌** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `generate_database_flattened_html_fixed.py` | ❌* | ❌* | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `generate_pcrai_from_db.py` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌*** | ❌*** | ❌*** | ❌ | ❌ | ❌ | ❌ | ❌ |
| `compare_k_parameters.py` | ✅ | ❌* | ✅ | ✅ | ✅**** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `generate_flattened_cusum_html.py` | ✅ | ❌* | ✅ | ✅ | ✅ | ✅***** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `generate_azure_report.py` | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `manage_example_ids.py` | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌****** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Legend:**
- ✅ = Parameter available
- ❌ = Parameter not applicable
- *Processes all by default
- **Modifies database in-place
- ***File-based, not ID-based processing
- ****Alias for --test-k
- *****Alias for --k
- ******Has --add/--remove instead of --ids

## Dependencies

- Python 3.x
- SQLite3
- NumPy
- tqdm (progress bars)
- argparse (command line parsing)

## File Structure
```
flatten/
├── apply_corrected_cusum_all.py          # CUSUM calculation
├── create_flattened_database_fast.py     # Database flattening
├── generate_flattened_cusum_html.py      # Configurable visualization ⭐
├── generate_database_flattened_html_fixed.py  # Database verification
├── generate_pcrai_from_db.py             # PCRAI export
├── compare_k_parameters.py               # K parameter comparison ⭐
├── generate_azure_report.py              # Azure report generation ⭐ (with smart y-axis scaling)
├── manage_example_ids.py                 # Example dataset management
├── extract_non_inverted_sigmoid_proper.py # Sigmoid filtering
├── create_database_from_csv.py           # Database creation
├── prepare_test_data.py                  # Test data prep
├── import_test_data.py                   # Test data import
├── import_azure_results.py               # Azure results import
├── import_pos_controls.py                # Control import
├── update_embed_from_csv.py              # Embedding updates
├── utils/                                # Shared utility modules
│   ├── database.py                       # Database functions
│   ├── algorithms.py                     # CUSUM and smoothing algorithms
│   └── visualization.py                  # SVG generation utilities
├── docs/                                 # Documentation
│   ├── command_line_flags_analysis.md
│   ├── curve_flattening_edge_cases_analysis.md
│   ├── flags_applicability_table.md
│   └── flags_table.md
└── input/                                # Source CSV and reference files
```

## License

[Add your license information here]
