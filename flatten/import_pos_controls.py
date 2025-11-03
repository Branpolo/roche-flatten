#!/usr/bin/env python3
"""
Import positive controls from CSV into database.

This script creates the pos_controls table and populates it with positive control
sample identifiers from controls.csv. Negative controls (NPC%, NTC%, NEG%) are
handled via pattern matching in report code and not stored in the database.
"""

import sqlite3
import csv
import argparse
import sys
from pathlib import Path


def create_pos_controls_table(conn):
    """Create the pos_controls table"""
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pos_controls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mix TEXT NOT NULL,
        target TEXT NOT NULL,
        control_sample TEXT NOT NULL,
        dye TEXT,
        UNIQUE(mix, target, control_sample)
    )
    """)

    conn.commit()
    print("pos_controls table created")


def import_controls(conn, csv_path, reset=False):
    """Import positive controls from CSV"""
    cursor = conn.cursor()

    # Reset table if requested
    if reset:
        cursor.execute("DELETE FROM pos_controls")
        conn.commit()
        print("Existing pos_controls data cleared")

    stats = {
        'total': 0,
        'imported': 0,
        'duplicates': 0,
        'errors': []
    }

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats['total'] += 1

            try:
                mix = row['mix'].strip().lower()
                target = row['target'].strip()
                control_sample = row['control label'].strip()
                dye = row['dye/detector'].strip() if 'dye/detector' in row else None

                # Skip empty rows
                if not mix or not target or not control_sample:
                    continue

                try:
                    cursor.execute("""
                        INSERT INTO pos_controls (mix, target, control_sample, dye)
                        VALUES (?, ?, ?, ?)
                    """, (mix, target, control_sample, dye))
                    stats['imported'] += 1
                except sqlite3.IntegrityError:
                    # Duplicate entry
                    stats['duplicates'] += 1

            except Exception as e:
                stats['errors'].append(f"Row {stats['total']}: {e}")
                continue

    conn.commit()

    # Print statistics
    print(f"\nImport complete:")
    print(f"  Total rows processed: {stats['total']}")
    print(f"  Successfully imported: {stats['imported']}")
    print(f"  Duplicates skipped: {stats['duplicates']}")

    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")
        for error in stats['errors'][:5]:  # Show first 5 errors
            print(f"    {error}")

    # Show what was imported
    cursor.execute("""
        SELECT mix, target, GROUP_CONCAT(control_sample, ', ') as controls
        FROM pos_controls
        GROUP BY mix, target
        ORDER BY mix, target
    """)

    print("\nPositive controls by mix-target:")
    for mix, target, controls in cursor.fetchall():
        print(f"  {mix.upper()}-{target}: {controls}")


def main():
    parser = argparse.ArgumentParser(
        description='Import positive control definitions from CSV'
    )
    parser.add_argument('--db', default='readings.db',
                       help='Path to SQLite database file (default: readings.db)')
    parser.add_argument('--csv', default='flatten/input/controls.csv',
                       help='Path to controls CSV file (default: flatten/input/controls.csv)')
    parser.add_argument('--reset', action='store_true',
                       help='Clear existing pos_controls data before importing')

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db).exists():
        print(f"Error: Database file not found: {args.db}")
        sys.exit(1)

    # Check if CSV exists
    if not Path(args.csv).exists():
        print(f"Error: CSV file not found: {args.csv}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(args.db)

    # Create table
    create_pos_controls_table(conn)

    # Import data
    import_controls(conn, args.csv, reset=args.reset)

    conn.close()
    print("\nDone!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
