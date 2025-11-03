# Claude Code Memory - Roche Flatten Project

## Important Reminders

### User Instructions
- **NEVER start implementation without all clarification questions answered** - Always wait for explicit user confirmation before proceeding with implementation
- When asking clarification questions, wait for complete user responses before beginning work
- Always put output files from py or other scripts in `/output_data`, otherwise finding and Git are complicated.

### Documentation Updates
- **ALWAYS update README.md when adding new features or parameters** - Document any new command-line flags, parameters, or functionality
- Update both the parameter descriptions and the parameter compatibility matrix when applicable
- Add usage examples for new features to help users understand how to use them

## Project Overview

This repository contains CUSUM analysis and curve flattening tools for PCR time-series data.

**Purpose**: CUSUM analysis and curve flattening for time series data
- **Active scripts**: `apply_corrected_cusum_all.py`, `create_flattened_database_fast.py`, `compare_k_parameters.py`, `generate_flattened_cusum_html.py`, etc.
- **Database**: `/home/azureuser/code/wssvc-flow/readings.db` (or custom path)
- **Output**: Flattened curves, PCRAI files, HTML visualizations
- **Documentation**: `flatten/docs/`

## Flatten Project Guidelines

### Project Context
- This is a slope detection and curve flattening project for time series data
- Database: SQLite database with readings, flatten, and example_ids tables
- CUSUM algorithm detects downward trends in PCR curves
- Working on curve flattening visualization for records with significant downward trends

### When Working on Flatten
- Run scripts from project root: `python3 flatten/script_name.py`
- Import from flatten utils: `from flatten.utils.algorithms import ...`
- Put outputs in `/output_data/` (shared output directory)
- Focus on mathematical analysis, CUSUM detection, curve flattening
- No report generation (HTML reports are for visualization only)

### Active Flatten Scripts
- `flatten/apply_corrected_cusum_all.py` - Calculate CUSUM values for all records
- `flatten/create_flattened_database_fast.py` - Create flattened database
- `flatten/generate_flattened_cusum_html.py` - Generate HTML visualizations
- `flatten/generate_database_flattened_html_fixed.py` - Verify database flattening
- `flatten/compare_k_parameters.py` - Compare CUSUM parameters
- `flatten/generate_pcrai_from_db.py` - Export PCRAI files
- `flatten/manage_example_ids.py` - Manage example dataset

## Bidirectional Flag Management

### When Creating New Functions
- Review all standard parameters in `flatten/docs/flags_table.md`
- Implement ALL applicable standard flags
- For any flag not implemented, provide explicit justification
- Update README.md with the new function's parameter support

### When Adding/Updating Flags
- **IMPORTANT**: When a new flag is added or updated, update ALL relevant functions that should support it
- Check these core scripts for flag applicability (all in `flatten/`):
  - `generate_flattened_cusum_html.py`
  - `create_flattened_database_fast.py`
  - `compare_k_parameters.py`
  - `generate_database_flattened_html_fixed.py`
  - `apply_corrected_cusum_all.py`
  - `generate_pcrai_from_db.py`
  - `manage_example_ids.py`
- Update README.md parameter compatibility matrix for all affected scripts
- Ensure consistent implementation across all scripts (same defaults, same help text)

## Standard Parameters Guidelines

### Overview
When building new Python scripts for the Flatten project, maintain consistency across the codebase by using the standard parameter set documented in `flatten/docs/flags_table.md`. This ensures uniform interfaces and improves maintainability.

### Standard Parameters Reference
Refer to `flatten/docs/flags_table.md` for the complete list of standard parameters and their current implementation status across existing flatten scripts.

### Implementation Requirements

#### 1. Consider All Standard Parameters
When creating new Python scripts, evaluate each of these standard parameters for applicability:

- `--all`: Process all available records/data
- `--files`: File-based operations
- `--db`: Database path specification
- `--output`: Output file/directory path
- `--default-k`: Default k parameter for comparisons
- `--test-k`: Test k parameter for comparisons
- `--cusum-limit`: CUSUM threshold limit
- `--k`: K parameter for algorithms
- `--ids`: Specific record IDs to process
- `--example-dataset`: Use example/sample data
- `--limit`: Limit number of records processed
- `--threshold`: Algorithm threshold values
- `--sort-order`: Sort direction (asc/desc)
- `--sort-by`: Sort field specification

#### 2. Justification Required
For any standard parameter that is **not** implemented in your new script, provide explicit justification such as:
- "can't add: processes all by default" (for --all)
- "can't add: not file-based" (for --files)
- "can't add: modifies DB in-place" (for --output)
- "can't add: no k parameter" (for k-related flags)

#### 3. Implementation Examples

**Database Parameter Implementation:**
```python
parser.add_argument('--db', default='readings.db',
                   help='Path to SQLite database file')
```

**Output Parameter Implementation:**
```python
parser.add_argument('--output',
                   help='Output file path (default: auto-generated)')
```

**Limit Parameter Implementation:**
```python
parser.add_argument('--limit', type=int,
                   help='Limit number of records to process')
```

**IDs Parameter Implementation:**
```python
parser.add_argument('--ids', nargs='+', type=int,
                   help='Specific record IDs to process')
```

**Sorting Parameters Implementation:**
```python
parser.add_argument('--sort-by',
                   choices=['id', 'timestamp', 'value'],
                   help='Field to sort by')
parser.add_argument('--sort-order',
                   choices=['asc', 'desc'], default='asc',
                   help='Sort order')
```

#### 4. Consistency Requirements
- Use identical parameter names and help text where possible
- Maintain consistent default values across scripts
- Follow existing patterns for parameter validation
- Ensure parameter behavior matches expectations from other scripts

#### 5. Priority Implementation
Based on the analysis in `flags_table.md`, prioritize these parameters for new scripts:
1. `--db`: Essential for database connectivity
2. `--output`: Important for scripts generating files
3. `--ids`, `--limit`: Useful for selective processing
4. `--threshold`, `--cusum-limit`: Important for algorithm parameters

### Validation
Before finalizing any new script, cross-reference with `flags_table.md` to ensure:
- All applicable standard parameters are implemented
- Non-applicable parameters are properly justified
- Implementation follows established patterns
- Parameter behavior is consistent with existing scripts
- Use reusable code where possible and if you can't use the reusable function consider if it can be extended
- Always follow DRY and YAGNI principles when planning and coding
- Unless user says not to, verify your work using the playwright mcp

## CUSUM Algorithm Guidelines

### k Parameter Selection
- **k=0.0**: Most sensitive, detects all changes (use for initial analysis)
- **k=0.1**: Moderate tolerance, filters small fluctuations (recommended for production)
- **k=0.2-0.3**: Higher tolerance, only significant trends

### Threshold Selection
- **Default: -80**: Balanced flattening (~10,534 of 19,120 curves)
- **Lower (e.g., -100)**: More selective, only flatten strong downward trends
- **Higher (e.g., -50)**: More aggressive, flatten more curves

### Sanity Checks
- **--sanity-check-slope**: Compare CUSUM min point reading with early cycle average
- **--sanity-lob**: Use Line of Best Fit gradient check (more robust for noisy data)

## Workflow Guidelines

### Standard Development Workflow
1. **Test on example dataset** (`--example-dataset` flag) - Quick validation with curated 34 IDs
2. **Test on specific IDs** (`--ids` flag) - Deep dive into problematic cases
3. **Test with limits** (`--limit` flag) - Sample larger dataset before full processing
4. **Run full processing** (`--all` or no flags) - Production processing

### Parameter Tuning Workflow
1. **Generate visualizations with different k values** using `generate_flattened_cusum_html.py`
2. **Compare k parameters** using `compare_k_parameters.py` to see which curves change
3. **Update database CUSUM** using `apply_corrected_cusum_all.py` with optimal k
4. **Create flattened database** using `create_flattened_database_fast.py`
5. **Verify flattening** using `generate_database_flattened_html_fixed.py`
6. **Export PCRAI files** using `generate_pcrai_from_db.py`

## Code Style and Best Practices

### Import Statements
```python
# For scripts in flatten/
from flatten.utils.algorithms import calculate_cusum, smooth_data
from flatten.utils.database import load_example_ids, get_readings
from flatten.utils.visualization import generate_svg_curve
```

### Database Connections
```python
import sqlite3

# Always parameterize database path
db_path = args.db if args.db else 'readings.db'
conn = sqlite3.connect(db_path)
```

### Error Handling
- Always validate database path exists before processing
- Handle missing tables gracefully (example_ids may not exist)
- Provide clear error messages for invalid IDs or missing data
- Log warnings for edge cases (shallow dips, noise)

### Output Files
- Always write to `output_data/` directory by default
- Use descriptive filenames with parameters: `example_cusum_k0.2_lim-80.html`
- Include metadata in HTML headers (date generated, parameters used)

## Testing and Verification

### Before Committing Changes
1. **Test with example dataset**: Verify output matches expectations
2. **Test edge cases**: ID 2112 (classic downward trend), ID 403 (shallow dip), ID 418 (noisy)
3. **Test parameter variations**: Different k values, thresholds, sanity checks
4. **Check HTML output**: Graphs render correctly, controls work

### Common Test Commands
```bash
# Quick test on example dataset
python3 flatten/generate_flattened_cusum_html.py --example-dataset --k 0.2 --limit 10

# Test specific edge cases
python3 flatten/generate_flattened_cusum_html.py --ids 2112,403,418 --k 0.1

# Test parameter comparison
python3 flatten/compare_k_parameters.py --default-k 0.0 --test-k 0.2 --example-dataset

# Verify database flattening
python3 flatten/generate_database_flattened_html_fixed.py --limit 20
```

## Common Issues and Solutions

### Issue: High Memory Usage with --all
**Solution**: Use `--limit` to process in batches, or use database-based sorting (`--sort-by db-cusum`)

### Issue: False Positives (Flattening Shallow Dips)
**Solution**: Enable `--sanity-check-slope` or `--sanity-lob` to filter out false positives

### Issue: CUSUM Values Don't Match Between Runs
**Solution**: Ensure consistent k parameter and threshold across scripts; check database has latest CUSUM values

### Issue: PCRAI Export Missing Mixes
**Solution**: Verify database has mix_name populated for all targets; check for NULL values

## Documentation Files

- `flatten/docs/command_line_flags_analysis.md` - Flag usage analysis
- `flatten/docs/curve_flattening_edge_cases_analysis.md` - Edge case documentation
- `flatten/docs/flags_applicability_table.md` - Flag applicability across scripts
- `flatten/docs/flags_table.md` - Complete parameter reference

## Performance Optimization

### Database Queries
- Use `in_use=1` filter to exclude filtered records
- Create indexes on frequently queried columns (id, filename, in_use)
- Use batch operations for updates (transaction with executemany)

### Memory Management
- Process records in batches when using --all
- Use generators instead of loading all data into memory
- Close database connections when done

### Visualization
- Limit HTML output with `--limit` for large datasets
- Use `--only-failed` to filter output to problematic cases only
- Consider generating separate HTML files per mix for large datasets
