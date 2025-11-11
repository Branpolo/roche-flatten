#!/usr/bin/env python3
"""
Rank CFD values per mix-target combination for Azure and AR results.

For each mix-target combination (excluding IC), ranks samples from lowest to highest CFD,
assigning sequential order numbers starting at 1. Both Azure and AR CFD values are ranked
independently in separate columns (azure_order and ar_order).

Only processes rows where BOTH Azure CFD and AR CFD are non-NULL.
"""

import sqlite3
import argparse
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description='Rank CFD values per mix-target combination'
    )
    parser.add_argument('--db', default='~/dbs/readings.db',
                       help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--table', default='readings',
                       choices=['readings', 'test_data', 'flatten', 'flatten_test'],
                       help='Table to update (default: readings)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')
    return parser.parse_args()


def main():
    args = parse_args()

    # Expand database path
    db_path = Path(args.db).expanduser()

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    print(f"Database: {db_path}")
    print(f"Target table: {args.table}")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    print()

    # Get all unique mix-target combinations (excluding IC)
    cursor.execute(f"""
        SELECT DISTINCT Mix, MixTarget
        FROM {args.table}
        WHERE MixTarget != 'IC' AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
        ORDER BY Mix, MixTarget
    """)
    combinations = cursor.fetchall()

    print(f"Found {len(combinations)} mix-target combinations to process\n")

    stats = {
        'total_combinations': len(combinations),
        'total_rows_ranked': 0,
        'combinations_processed': 0
    }

    # Process each combination
    for mix, mixtarget in combinations:
        # Get all rows for this combination with both CFD values
        cursor.execute(f"""
            SELECT id, AzureCFD, ar_cfd
            FROM {args.table}
            WHERE Mix = ? AND MixTarget = ? AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
            ORDER BY AzureCFD ASC
        """, (mix, mixtarget))

        azure_rows = cursor.fetchall()

        if not azure_rows:
            continue

        # Rank Azure CFD (sorted by AzureCFD ascending)
        azure_update_values = []
        for rank, (row_id, azure_cfd, ar_cfd) in enumerate(azure_rows, start=1):
            azure_update_values.append((rank, row_id))

        # Get rows sorted by ar_cfd for AR ranking
        cursor.execute(f"""
            SELECT id, AzureCFD, ar_cfd
            FROM {args.table}
            WHERE Mix = ? AND MixTarget = ? AND AzureCFD IS NOT NULL AND ar_cfd IS NOT NULL
            ORDER BY ar_cfd ASC
        """, (mix, mixtarget))

        ar_rows = cursor.fetchall()

        # Rank AR CFD (sorted by ar_cfd ascending)
        ar_update_values = []
        for rank, (row_id, azure_cfd, ar_cfd) in enumerate(ar_rows, start=1):
            ar_update_values.append((rank, row_id))

        # Update database
        if not args.dry_run:
            # Update azure_order
            cursor.executemany(f"""
                UPDATE {args.table}
                SET azure_order = ?
                WHERE id = ?
            """, azure_update_values)

            # Update ar_order
            cursor.executemany(f"""
                UPDATE {args.table}
                SET ar_order = ?
                WHERE id = ?
            """, ar_update_values)

            stats['total_rows_ranked'] += len(azure_rows)
            stats['combinations_processed'] += 1
            print(f"✓ {mix}-{mixtarget}: {len(azure_rows)} rows ranked")
        else:
            stats['total_rows_ranked'] += len(azure_rows)
            stats['combinations_processed'] += 1
            print(f"  {mix}-{mixtarget}: Would rank {len(azure_rows)} rows")

    if not args.dry_run:
        conn.commit()
        print("\nChanges committed to database.")
    else:
        print("\nDry run complete - no changes made.")

    conn.close()

    # Print statistics
    print("\n" + "="*60)
    print("RANKING STATISTICS")
    print("="*60)
    print(f"Total combinations processed: {stats['combinations_processed']}")
    print(f"Total rows ranked:            {stats['total_rows_ranked']}")

    print("\nRanking complete!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
