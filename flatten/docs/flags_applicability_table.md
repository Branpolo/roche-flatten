# Command Line Flags Applicability Table

## Table: Flags (columns) × Python Scripts (rows)

| Script / Flag | --all | --files | --db | --output | --default-k | --test-k | --cusum-limit | --k | --ids | --example-dataset | --limit | --threshold | --sort-order | --sort-by |
|--------------|-------|---------|------|----------|-------------|----------|---------------|-----|-------|-------------------|---------|-------------|--------------|-----------|
| **apply_corrected_cusum_all.py** | can't add: processes all by default | can't add: not file-based | can add | can add | can't add: doesn't compare k | can't add: doesn't compare k | can add | can add | can add | can add | can add | can add | can add | can add |
| **create_flattened_database_fast.py** | can't add: processes all by default | can't add: not file-based | can add | can't add: modifies DB in-place | can't add: no k parameter | can't add: no k parameter | can add | can't add: no k parameter | can add | can add | can add | can add | can add | can add |
| **generate_database_flattened_html_fixed.py** | can't add: processes all by default | can't add: not file-based | can add | can add | can't add: no k parameter | can't add: no k parameter | can add | can't add: no k parameter | can add | can add | can add | can add | can add | can add |
| **generate_pcrai_from_db.py** | present | present | present | present | can't add: no k parameter | can't add: no k parameter | can't add: no CUSUM thresholds | can't add: no k parameter | can't add: file-based not ID-based | can't add: file-based not ID-based | can't add: file-based processing | can't add: no CUSUM thresholds | can't add: generates files not display | can't add: generates files not display |
| **compare_k_parameters.py** | can add | can't add: not file-based | can add | can add | present | present | present | can add | present | present | present | can add | can add | can add |
| **generate_flattened_cusum_html.py** | can add | can't add: not file-based | can add | can add | can add | can't add: single k tool | can add | present | present | present | present | present | present | present |

## Legend:
- **present**: Flag is already implemented in the script
- **can add**: Flag could be added to enhance functionality
- **can't add**: Flag doesn't make sense for this script's purpose (with brief reason)