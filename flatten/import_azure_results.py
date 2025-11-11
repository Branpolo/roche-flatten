#!/usr/bin/env python3
"""
Import Azure classification results (AzureCls and AzureCFD) from CSV into database.

This script reads CSV files containing Azure classification results and updates
the database with AzureCls (integer) and AzureCFD (float) values.

The unique identifier is FileUID-Tube-MixTarget.
Before updating, the script verifies that the Sample name matches in both
CSV and database for sanity checking.

Special rule: If AzureAmb == 1, AzureCls is set to 2 (ambiguous classification).
"""

import sqlite3
import csv
import argparse
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description='Import Azure or AR (Azure Results) classification results from CSV to database'
    )
    parser.add_argument('--db', default='~/dbs/readings.db',
                       help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--csv', required=True,
                       help='Path to CSV file containing Azure/AR results')
    parser.add_argument('--table', default='readings',
                       choices=['readings', 'test_data', 'flatten', 'flatten_test', 'all_readings'],
                       help='Table to update (default: readings)')
    parser.add_argument('--ar-results', action='store_true',
                       help='Import as AR (Azure Results) data instead of Azure data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')
    return parser.parse_args()


def main():
    args = parse_args()

    # Expand paths
    csv_path = Path(args.csv)
    db_path = Path(args.db).expanduser()

    # Check if CSV file exists
    if not csv_path.exists():
        print(f"Error: CSV file not found: {args.csv}")
        sys.exit(1)

    # Check if database exists
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Statistics
    stats = {
        'total_rows': 0,
        'matched': 0,
        'updated': 0,
        'sample_mismatch': 0,
        'not_found': 0,
        'amb_override': 0,  # Count where AzureAmb=1 forced AzureCls=2
        'errors': []
    }

    # Determine import mode and set column names
    if args.ar_results:
        import_mode = "AR Results"
        cls_col = 'ar_cls'
        amb_col = 'ar_amb'
        cfd_col = 'ar_cfd'
        ct_col = 'ar_ct'
    else:
        import_mode = "Azure"
        cls_col = 'AzureCls'
        amb_col = 'AzureAmb'
        cfd_col = 'AzureCFD'
        ct_col = None  # Azure doesn't have CT column in output

    print(f"Reading CSV: {args.csv}")
    print(f"Import mode: {import_mode}")
    print(f"Database: {args.db}")
    print(f"Target table: {args.table}")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    print()

    with open(args.csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)

        # Find column indices
        try:
            sample_idx = header.index('Sample')
            file_idx = header.index('File')  # Use File instead of FileUID
            mix_idx = header.index('Mix')
            mixtarget_idx = header.index('MixTarget')
            tube_idx = header.index('Tube')
            cls_idx = header.index('AzureCls')  # CSV always has AzureCls
            amb_idx = header.index('AzureAmb')  # CSV always has AzureAmb
            cfd_idx = header.index('AzureCFD')  # CSV always has AzureCFD
            # CT column is optional
            try:
                ct_idx = header.index('AzureCT') if args.ar_results else None
            except ValueError:
                ct_idx = None
        except ValueError as e:
            print(f"Error: Required column not found in CSV: {e}")
            sys.exit(1)

        for row in reader:
            if len(row) < max(sample_idx, file_idx, mix_idx, mixtarget_idx, tube_idx, cls_idx, amb_idx, cfd_idx) + 1:
                continue

            stats['total_rows'] += 1

            # Extract data from CSV
            csv_sample = row[sample_idx].strip()
            csv_file = row[file_idx].strip()
            csv_mix = row[mix_idx].strip()
            csv_mixtarget = row[mixtarget_idx].strip()
            csv_tube = row[tube_idx].strip()

            # Parse classification, ambiguity, and confidence values
            try:
                cls_csv = int(row[cls_idx]) if row[cls_idx].strip() else None
            except (ValueError, IndexError):
                cls_csv = None

            try:
                amb = int(row[amb_idx]) if row[amb_idx].strip() else 0
            except (ValueError, IndexError):
                amb = 0

            try:
                cfd = float(row[cfd_idx]) if row[cfd_idx].strip() else None
            except (ValueError, IndexError):
                cfd = None

            # Parse CT value if present
            ct_val = None
            if ct_idx is not None:
                try:
                    ct_val = float(row[ct_idx]) if row[ct_idx].strip() else None
                except (ValueError, IndexError):
                    ct_val = None

            # Skip if AzureCFD is NULL (required for reimport)
            if cfd is None:
                continue

            # Apply the rule: if Amb == 1, override Cls to 2
            if amb == 1:
                cls = 2
                stats['amb_override'] += 1
            else:
                cls = cls_csv

            # Create unique identifier (using File instead of FileUID)
            unique_id = f"{csv_file}-{csv_tube}-{csv_mix}-{csv_mixtarget}"

            # Find matching record in database using File column
            # Note: all_readings uses rowid, while other tables use id
            if args.table == 'all_readings':
                cursor.execute(f"""
                    SELECT rowid, Sample
                    FROM {args.table}
                    WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
                """, (csv_file, csv_tube, csv_mix, csv_mixtarget))
            else:
                cursor.execute(f"""
                    SELECT id, Sample
                    FROM {args.table}
                    WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
                """, (csv_file, csv_tube, csv_mix, csv_mixtarget))

            result = cursor.fetchone()

            if result:
                db_id, db_sample = result
                stats['matched'] += 1

                # Sanity check: verify sample names match
                if db_sample != csv_sample:
                    stats['sample_mismatch'] += 1
                    error_msg = f"Sample mismatch for {unique_id}: DB='{db_sample}' vs CSV='{csv_sample}'"
                    stats['errors'].append(error_msg)
                    if len(stats['errors']) <= 10:  # Only print first 10 errors
                        print(f"WARNING: {error_msg}")
                    continue

                # Update the record
                if not args.dry_run:
                    # Determine WHERE clause based on table
                    where_clause = "WHERE rowid = ?" if args.table == 'all_readings' else "WHERE id = ?"

                    if args.ar_results:
                        # Update AR columns
                        if ct_val is not None:
                            cursor.execute(f"""
                                UPDATE {args.table}
                                SET {cls_col} = ?, {amb_col} = ?, {cfd_col} = ?, {ct_col} = ?
                                {where_clause}
                            """, (cls, amb, cfd, ct_val, db_id))
                        else:
                            cursor.execute(f"""
                                UPDATE {args.table}
                                SET {cls_col} = ?, {amb_col} = ?, {cfd_col} = ?
                                {where_clause}
                            """, (cls, amb, cfd, db_id))
                    else:
                        # Update Azure columns
                        cursor.execute(f"""
                            UPDATE {args.table}
                            SET {cls_col} = ?, {amb_col} = ?, {cfd_col} = ?
                            {where_clause}
                        """, (cls, amb, cfd, db_id))
                    stats['updated'] += 1
                else:
                    stats['updated'] += 1
                    if stats['updated'] <= 5:  # Show first 5 updates in dry-run
                        if args.ar_results:
                            print(f"Would update {unique_id}: ar_cls={cls}, ar_amb={amb}, ar_cfd={cfd}" + (f", ar_ct={ct_val}" if ct_val else ""))
                        else:
                            print(f"Would update {unique_id}: AzureCls={cls}, AzureAmb={amb}, AzureCFD={cfd}")
            else:
                stats['not_found'] += 1
                error_msg = f"Record not found in DB: {unique_id} (Sample: {csv_sample})"
                stats['errors'].append(error_msg)
                if len(stats['errors']) <= 10:
                    print(f"WARNING: {error_msg}")

    if not args.dry_run:
        conn.commit()
        print("\nChanges committed to database.")
    else:
        print("\nDry run complete - no changes made.")

    conn.close()

    # Print statistics
    print("\n" + "="*60)
    print("IMPORT STATISTICS")
    print("="*60)
    print(f"Total CSV rows processed:     {stats['total_rows']}")
    print(f"Records matched in DB:        {stats['matched']}")
    print(f"Records updated:              {stats['updated']}")
    print(f"AzureAmb=1 overrides:         {stats['amb_override']}")
    print(f"Sample name mismatches:       {stats['sample_mismatch']}")
    print(f"Records not found in DB:      {stats['not_found']}")
    print(f"Total errors:                 {len(stats['errors'])}")

    if stats['errors'] and len(stats['errors']) > 10:
        print(f"\n(Showing first 10 errors, {len(stats['errors']) - 10} more not shown)")

    if stats['sample_mismatch'] > 0 or stats['not_found'] > 0:
        print("\nWARNING: Some records had issues. Review the warnings above.")
        return 1

    print("\nImport completed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
