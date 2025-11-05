#!/usr/bin/env python3
"""
Update EmbedCT and EmbedRFU in readings and flatten tables from Roche embed CSV.

This script reads the roche_wssvc_embed.csv file and updates the EmbedCT and EmbedRFU
columns in both the readings and flatten tables, using the composite indexes for efficient matching.
"""

import sqlite3
import csv
import argparse
from pathlib import Path

def update_embed_data(db_path, csv_path, dry_run=False):
    """Update EmbedCT and EmbedRFU from CSV file."""

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Read CSV and prepare updates
    print(f"Reading CSV from {csv_path}...")
    updates_readings = []
    updates_flatten = []
    updates_test_data = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract values
            file = row['File']
            tube = row['Tube']
            mix = row['Mix']
            mix_target = row['MixTarget']  # CSV has this pre-computed
            embed_ct = row['Embed.CT'] if row['Embed.CT'] else None
            embed_rfu = row['Embed.RFU'] if row['Embed.RFU'] else None

            # Convert empty strings to None
            if embed_ct == '':
                embed_ct = None
            if embed_rfu == '':
                embed_rfu = None

            updates_readings.append((embed_ct, embed_rfu, file, tube, mix, mix_target))
            updates_flatten.append((embed_ct, embed_rfu, file, tube, mix, mix_target))
            updates_test_data.append((embed_ct, embed_rfu, file, tube, mix, mix_target))

    print(f"Prepared {len(updates_readings)} updates from CSV")

    if dry_run:
        print("\n** DRY RUN MODE - No changes will be made **")
        print(f"\nWould update {len(updates_readings)} rows in readings table")
        print(f"Would update {len(updates_flatten)} rows in flatten table")
        print(f"Would update {len(updates_test_data)} rows in test_data table")

        # Show sample
        print("\nSample update (first 3):")
        for i, update in enumerate(updates_readings[:3]):
            print(f"  {i+1}. File={update[2]}, Tube={update[3]}, Mix={update[4]}, MixTarget={update[5]}")
            print(f"     EmbedCT={update[0]}, EmbedRFU={update[1]}")

        conn.close()
        return

    # Update readings table
    print("\nUpdating readings table...")
    update_sql = """
        UPDATE readings
        SET EmbedCT = ?, EmbedRFU = ?
        WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
    """

    cursor.executemany(update_sql, updates_readings)
    readings_updated = cursor.rowcount
    print(f"Updated {readings_updated} rows in readings table")

    # Update flatten table
    print("\nUpdating flatten table...")
    update_sql_flatten = """
        UPDATE flatten
        SET EmbedCT = ?, EmbedRFU = ?
        WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
    """

    cursor.executemany(update_sql_flatten, updates_flatten)
    flatten_updated = cursor.rowcount
    print(f"Updated {flatten_updated} rows in flatten table")

    # Update test_data table
    print("\nUpdating test_data table...")
    update_sql_test = """
        UPDATE test_data
        SET EmbedCT = ?, EmbedRFU = ?
        WHERE File = ? AND Tube = ? AND Mix = ? AND MixTarget = ?
    """

    cursor.executemany(update_sql_test, updates_test_data)
    test_data_updated = cursor.rowcount
    print(f"Updated {test_data_updated} rows in test_data table")

    # Commit changes
    conn.commit()

    # Verify some updates
    print("\nVerifying updates...")
    cursor.execute("""
        SELECT COUNT(*) FROM readings
        WHERE EmbedCT IS NOT NULL OR EmbedRFU IS NOT NULL
    """)
    readings_with_embed = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM flatten
        WHERE EmbedCT IS NOT NULL OR EmbedRFU IS NOT NULL
    """)
    flatten_with_embed = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM test_data
        WHERE EmbedCT IS NOT NULL OR EmbedRFU IS NOT NULL
    """)
    test_data_with_embed = cursor.fetchone()[0]

    print(f"readings table: {readings_with_embed} rows with EmbedCT/EmbedRFU values")
    print(f"flatten table: {flatten_with_embed} rows with EmbedCT/EmbedRFU values")
    print(f"test_data table: {test_data_with_embed} rows with EmbedCT/EmbedRFU values")

    conn.close()
    print("\n✓ Update complete!")

def main():
    parser = argparse.ArgumentParser(
        description='Update EmbedCT and EmbedRFU from Roche embed CSV file'
    )
    parser.add_argument('--db',
                       default='~/dbs/readings.db',
                       help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--csv',
                       default='flatten/input/roche_wssvc_embed.csv',
                       help='Path to CSV file with embed data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')

    args = parser.parse_args()

    # Validate files exist
    if not Path(args.db).exists():
        print(f"Error: Database not found at {args.db}")
        return 1

    if not Path(args.csv).exists():
        print(f"Error: CSV file not found at {args.csv}")
        return 1

    update_embed_data(args.db, args.csv, args.dry_run)
    return 0

if __name__ == '__main__':
    exit(main())
