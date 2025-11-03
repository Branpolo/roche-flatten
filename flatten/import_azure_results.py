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
        description='Import Azure classification results from CSV to database'
    )
    parser.add_argument('--db', default='readings.db',
                       help='Path to SQLite database file (default: readings.db)')
    parser.add_argument('--csv', required=True,
                       help='Path to CSV file containing Azure results')
    parser.add_argument('--table', default='readings',
                       choices=['readings', 'test_data', 'flatten', 'flatten_test'],
                       help='Table to update (default: readings)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')
    return parser.parse_args()


def main():
    args = parse_args()

    # Check if CSV file exists
    if not Path(args.csv).exists():
        print(f"Error: CSV file not found: {args.csv}")
        sys.exit(1)

    # Check if database exists
    if not Path(args.db).exists():
        print(f"Error: Database file not found: {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
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

    print(f"Reading CSV: {args.csv}")
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
            azurecls_idx = header.index('AzureCls')
            azureamb_idx = header.index('AzureAmb')
            azurecfd_idx = header.index('AzureCFD')
        except ValueError as e:
            print(f"Error: Required column not found in CSV: {e}")
            sys.exit(1)

        for row in reader:
            if len(row) < max(sample_idx, file_idx, mix_idx, mixtarget_idx, tube_idx, azurecls_idx, azureamb_idx, azurecfd_idx) + 1:
                continue

            stats['total_rows'] += 1

            # Extract data from CSV
            csv_sample = row[sample_idx].strip()
            csv_file = row[file_idx].strip()
            csv_mix = row[mix_idx].strip()
            csv_mixtarget = row[mixtarget_idx].strip()
            csv_tube = row[tube_idx].strip()

            # Parse AzureCls, AzureAmb, and AzureCFD
            try:
                azure_cls_csv = int(row[azurecls_idx]) if row[azurecls_idx].strip() else None
            except (ValueError, IndexError):
                azure_cls_csv = None

            try:
                azure_amb = int(row[azureamb_idx]) if row[azureamb_idx].strip() else 0
            except (ValueError, IndexError):
                azure_amb = 0

            try:
                azure_cfd = float(row[azurecfd_idx]) if row[azurecfd_idx].strip() else None
            except (ValueError, IndexError):
                azure_cfd = None

            # Apply the rule: if AzureAmb == 1, override AzureCls to 2
            if azure_amb == 1:
                azure_cls = 2
                stats['amb_override'] += 1
            else:
                azure_cls = azure_cls_csv

            # Skip if both are None
            if azure_cls is None and azure_cfd is None:
                continue

            # Create unique identifier (using File instead of FileUID)
            unique_id = f"{csv_file}-{csv_tube}-{csv_mix}-{csv_mixtarget}"

            # Find matching record in database using File column
            cursor.execute(f"""
                SELECT id, Sample, AzureCls, AzureCFD
                FROM {args.table}
                WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
            """, (csv_file, csv_tube, csv_mix, csv_mixtarget))

            result = cursor.fetchone()

            if result:
                db_id, db_sample, db_azurecls, db_azurecfd = result
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
                    cursor.execute(f"""
                        UPDATE {args.table}
                        SET AzureCls = ?, AzureCFD = ?
                        WHERE id = ?
                    """, (azure_cls, azure_cfd, db_id))
                    stats['updated'] += 1
                else:
                    stats['updated'] += 1
                    if stats['updated'] <= 5:  # Show first 5 updates in dry-run
                        print(f"Would update {unique_id}: AzureCls={azure_cls}, AzureCFD={azure_cfd}")
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
