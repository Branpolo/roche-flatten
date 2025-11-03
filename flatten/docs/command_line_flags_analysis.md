# Command Line Flags Analysis for WSSVC Flow Scripts

## 1. Complete List of All Command Line Flags

### From `generate_pcrai_from_db.py`:
- `--all` (action='store_true') - Generate PCRAI for all unique filenames
- `--files` (str) - Generate PCRAI for specific files (comma-separated)  
- `--db` (str, default="/home/azureuser/code/wssvc-flow/readings.db") - Path to database file
- `--output` (str, default="output_data") - Output directory for PCRAI files

### From `compare_k_parameters.py`:
- `--default-k` (float, default=0.0) - Default CUSUM tolerance parameter k
- `--test-k` (float, required) - Test CUSUM tolerance parameter k to compare against default
- `--cusum-limit` (float, default=-80) - CUSUM threshold for flattening
- `--ids` (str) - Comma-separated list of specific IDs to process
- `--example-dataset` (action='store_true') - Use example dataset from feedback plots
- `--limit` (int) - Limit number of curves to process

### From `generate_flattened_cusum_html.py`:
- `--k` (float, default=0.0) - CUSUM tolerance parameter k
- `--ids` (str) - Comma-separated list of specific IDs to process  
- `--example-dataset` (action='store_true') - Use example dataset from feedback plots
- `--limit` (int) - Limit number of curves to process
- `--threshold` (float, default=-80) - CUSUM threshold for flattening
- `--sort-order` (choices=['up', 'down'], default='down') - Sort order for output
- `--sort-by` (choices=['cusum', 'db-cusum', 'id'], default='cusum') - Sort by criteria

## 2. Applicability Matrix

| Flag | apply_corrected_cusum_all.py | create_flattened_database_fast.py | generate_database_flattened_html_fixed.py | generate_pcrai_from_db.py | compare_k_parameters.py | generate_flattened_cusum_html.py |
|------|------------------------------|-----------------------------------|-------------------------------------------|--------------------------|------------------------|--------------------------------|
| `--all` | Can't add: processes all records by default | Can't add: processes all records by default | Can't add: processes all records by default | **Present** | Can add: alternative to --ids/--example-dataset | Can add: alternative to --ids/--example-dataset |
| `--files` | Can't add: not file-based processing | Can't add: not file-based processing | Can't add: not file-based processing | **Present** | Can't add: not file-based processing | Can't add: not file-based processing |
| `--db` | Can add: currently hardcoded path | Can add: currently hardcoded path | Can add: currently hardcoded path | **Present** | Can add: currently hardcoded path | Can add: currently hardcoded path |
| `--output` | Can add: no output directory control | Can't add: modifies database in-place | Can add: no output directory control | **Present** | Can add: no output directory control | Can add: no output directory control |
| `--default-k` | Can't add: doesn't compare k values | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | **Present** | Can add: could be baseline comparison |
| `--test-k` | Can't add: doesn't compare k values | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | **Present** | Can't add: single k parameter tool |
| `--cusum-limit` | Can add: currently hardcoded -80 threshold | Can add: currently hardcoded -80 threshold | Can add: currently hardcoded -80 threshold | Can't add: doesn't use CUSUM thresholds | **Present** | Can add: same as --threshold |
| `--k` | Can add: currently hardcoded k=0.0 | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | Can't add: doesn't use k parameter | Can add: same as --default-k | **Present** |
| `--ids` | Can add: currently processes all records | Can add: currently processes all records | Can add: currently processes all records | Can't add: file-based not record-based | **Present** | **Present** |
| `--example-dataset` | Can add: currently processes all records | Can add: currently processes all records | Can add: currently processes all records | Can't add: file-based not record-based | **Present** | **Present** |
| `--limit` | Can add: no limit control currently | Can add: no limit control currently | Can add: no limit control currently | Can't add: file-based processing | **Present** | **Present** |
| `--threshold` | Can add: currently hardcoded -80 | Can add: currently hardcoded -80 | Can add: currently hardcoded -80 | Can't add: doesn't use CUSUM thresholds | Can add: same as --cusum-limit | **Present** |
| `--sort-order` | Can add: no sorting control | Can add: no sorting control | Can add: no sorting control | Can't add: generates files not displays | Can add: comparison output sorting | **Present** |
| `--sort-by` | Can add: no sorting control | Can add: no sorting control | Can add: no sorting control | Can't add: generates files not displays | Can add: comparison output sorting | **Present** |

## 3. Priority Recommendations for Adding Flags

### High Priority (Should Add):
- `--db` to scripts without it (apply_corrected_cusum_all.py, create_flattened_database_fast.py, generate_database_flattened_html_fixed.py, compare_k_parameters.py, generate_flattened_cusum_html.py) 
- `--ids` and `--example-dataset` to scripts without it (apply_corrected_cusum_all.py, create_flattened_database_fast.py, generate_database_flattened_html_fixed.py)
- `--limit` to scripts without it (apply_corrected_cusum_all.py, create_flattened_database_fast.py, generate_database_flattened_html_fixed.py)

### Medium Priority (Could Add):
- `--threshold`/`--cusum-limit` standardization across CUSUM-using scripts
- `--output` for scripts that generate files
- `--k` parameter for scripts that could benefit from variable k values

### Low Priority (Optional):
- `--sort-order` and `--sort-by` for scripts that generate multiple outputs
- `--all` flag for scripts that currently process everything by default

## 4. Scripts Needing Argparse Addition:
1. `apply_corrected_cusum_all.py` - Would benefit from --db, --ids, --example-dataset, --limit, --k flags
2. `create_flattened_database_fast.py` - Would benefit from --db, --ids, --example-dataset, --limit, --threshold flags  
3. `generate_database_flattened_html_fixed.py` - Would benefit from --db, --ids, --example-dataset, --limit, --output, --sort-order, --sort-by flags