#!/usr/bin/env python3
"""
Migration script to add mix and target columns to example_ids table.

This script:
1. Adds 'mix' and 'target' columns to the example_ids table (nullable)
2. Creates a composite index on (id, mix, target) for performance
3. Preserves all existing data
"""

import sqlite3
import argparse
import sys


def migrate_example_ids_table(db_path):
    """
    Add mix and target columns to example_ids table and create index.

    Args:
        db_path: Path to SQLite database file

    Returns:
        True if migration successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if example_ids table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
        if not cursor.fetchone():
            print("ERROR: example_ids table does not exist in database")
            print("Please run manage_example_ids.py first to create the table")
            return False

        # Check current schema
        cursor.execute("PRAGMA table_info(example_ids)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        print(f"Current schema: {list(columns.keys())}")

        # Check if migration already done
        if 'mix' in columns and 'target' in columns:
            print("Migration already complete - mix and target columns exist")

            # Check if index exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_example_ids_mix_target'")
            if cursor.fetchone():
                print("Index idx_example_ids_mix_target already exists")
                return True
            else:
                print("Creating missing index...")
                cursor.execute("""
                    CREATE INDEX idx_example_ids_mix_target
                    ON example_ids(id, mix, target)
                """)
                conn.commit()
                print("Index created successfully")
                return True

        # Perform migration
        print("\nStarting migration...")

        # Step 1: Add mix column
        if 'mix' not in columns:
            print("Adding 'mix' column (TEXT NULL)...")
            cursor.execute("ALTER TABLE example_ids ADD COLUMN mix TEXT NULL")
            print("✓ mix column added")
        else:
            print("✓ mix column already exists")

        # Step 2: Add target column
        if 'target' not in columns:
            print("Adding 'target' column (TEXT NULL)...")
            cursor.execute("ALTER TABLE example_ids ADD COLUMN target TEXT NULL")
            print("✓ target column added")
        else:
            print("✓ target column already exists")

        # Step 3: Create composite index
        print("Creating composite index idx_example_ids_mix_target...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_example_ids_mix_target
            ON example_ids(id, mix, target)
        """)
        print("✓ Index created")

        # Commit changes
        conn.commit()

        # Verify migration
        cursor.execute("PRAGMA table_info(example_ids)")
        new_columns = {row[1]: row[2] for row in cursor.fetchall()}
        print(f"\nNew schema: {list(new_columns.keys())}")

        # Count existing records
        cursor.execute("SELECT COUNT(*) FROM example_ids")
        count = cursor.fetchone()[0]
        print(f"Preserved {count} existing example IDs")

        # Show sample data
        if count > 0:
            cursor.execute("SELECT id, mix, target FROM example_ids LIMIT 5")
            print("\nSample data (first 5 records):")
            for row in cursor.fetchall():
                print(f"  ID: {row[0]}, Mix: {row[1]}, Target: {row[2]}")

        conn.close()
        print("\n✓ Migration completed successfully!")
        return True

    except sqlite3.Error as e:
        print(f"ERROR: Database error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Migrate example_ids table to support mix and target columns'
    )
    parser.add_argument('--db', default='~/dbs/readings.db',
                       help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')

    args = parser.parse_args()

    # Expand user path
    import os
    db_path = os.path.expanduser(args.db)

    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Database: {db_path}")

    if args.dry_run:
        print("\nDRY RUN MODE - No changes will be made")
        print("Would add:")
        print("  - Column: mix (TEXT NULL)")
        print("  - Column: target (TEXT NULL)")
        print("  - Index: idx_example_ids_mix_target (id, mix, target)")
        return

    success = migrate_example_ids_table(db_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
