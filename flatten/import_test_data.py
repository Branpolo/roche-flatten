#!/usr/bin/env python3
"""Import CSV data into the SQLite pipeline tables.

Historically this script hard-coded the CSV path and always dropped/recreated
the ``test_data`` table. The new CLI options make it flexible enough to append
new runs (e.g., WS SVC hospital drops) directly into ``all_readings`` or any
other compatible table without destroying existing data.
"""

import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path


TEST_DATA_SCHEMA = '''
CREATE TABLE test_data (
    Sample TEXT,
    File TEXT,
    FileUID TEXT,
    Extension TEXT,
    Parser TEXT,
    Mix TEXT,
    MixTarget_Full TEXT,
    MixTarget TEXT,
    MixDetector TEXT,
    Group_Name TEXT,
    Target TEXT,
    Detector TEXT,
    Type TEXT,
    Role TEXT,
    Tube TEXT,
    ActiveLearnerResponse INTEGER,
    AzureCls INTEGER,
    AzureAmb INTEGER,
    AzureCFD REAL,
    EmbedCls REAL,
    EmbedCFD REAL,
    Results REAL,
    readings0 REAL,
    readings1 REAL,
    readings2 REAL,
    readings3 REAL,
    readings4 REAL,
    readings5 REAL,
    readings6 REAL,
    readings7 REAL,
    readings8 REAL,
    readings9 REAL,
    readings10 REAL,
    readings11 REAL,
    readings12 REAL,
    readings13 REAL,
    readings14 REAL,
    readings15 REAL,
    readings16 REAL,
    readings17 REAL,
    readings18 REAL,
    readings19 REAL,
    readings20 REAL,
    readings21 REAL,
    readings22 REAL,
    readings23 REAL,
    readings24 REAL,
    readings25 REAL,
    readings26 REAL,
    readings27 REAL,
    readings28 REAL,
    readings29 REAL,
    readings30 REAL,
    readings31 REAL,
    readings32 REAL,
    readings33 REAL,
    readings34 REAL,
    readings35 REAL,
    readings36 REAL,
    readings37 REAL,
    readings38 REAL,
    readings39 REAL,
    readings40 REAL,
    readings41 REAL,
    readings42 REAL,
    readings43 REAL
)
'''


BASE_COLUMNS = [
    'Sample', 'File', 'FileUID', 'Extension', 'Parser', 'Mix',
    'MixTarget_Full', 'MixTarget', 'MixDetector', 'Group_Name',
    'Target', 'Detector', 'Type', 'Role', 'Tube',
    'ActiveLearnerResponse', 'AzureCls', 'AzureAmb', 'AzureCFD',
    'EmbedCls', 'EmbedCFD', 'Results'
] + [f'readings{i}' for i in range(44)]


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def ensure_table(cursor, table_name, recreate):
    exists = table_exists(cursor, table_name)

    if recreate:
        if table_name != 'test_data':
            print("ERROR: --recreate-table is only supported for the test_data table")
            sys.exit(1)
        if exists:
            cursor.execute(f"DROP TABLE {table_name}")
            exists = False

    if not exists:
        if table_name != 'test_data':
            print(f"ERROR: Table '{table_name}' does not exist. Create it first or import into test_data.")
            sys.exit(1)
        cursor.execute(TEST_DATA_SCHEMA)
        print("Created test_data table")
    else:
        print(f"Using existing {table_name} table")


def get_table_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def build_insert_columns(available_columns, include_source_table):
    columns = []
    lower_available = {col.lower(): col for col in available_columns}

    def maybe_add(col_name):
        col = lower_available.get(col_name.lower())
        if col:
            columns.append(col)
            return True
        return False

    if include_source_table:
        maybe_add('source_table')

    missing = []
    for base in BASE_COLUMNS:
        if not maybe_add(base):
            missing.append(base)

    if missing:
        print("WARNING: The following columns were not found in the target table and will be skipped:")
        for col in missing:
            print(f"  - {col}")

    if not columns:
        print("ERROR: No matching columns found to insert into the target table.")
        sys.exit(1)

    return columns


def row_value(row, index, cast=None):
    if len(row) <= index:
        return None
    raw = row[index].strip()
    if raw == '':
        return None
    if cast:
        try:
            return cast(raw)
        except ValueError:
            return None
    return raw


def build_row_dict(csv_row):
    data = {
        'Sample': row_value(csv_row, 0),
        'File': row_value(csv_row, 1),
        'FileUID': row_value(csv_row, 2),
        'Extension': row_value(csv_row, 3),
        'Parser': row_value(csv_row, 4),
        'Mix': row_value(csv_row, 5),
        'MixTarget_Full': row_value(csv_row, 6),
        'MixTarget': row_value(csv_row, 7),
        'MixDetector': row_value(csv_row, 8),
        'Group_Name': row_value(csv_row, 10),
        'Target': row_value(csv_row, 11),
        'Detector': row_value(csv_row, 12),
        'Type': row_value(csv_row, 15),
        'Role': row_value(csv_row, 16),
        'Tube': row_value(csv_row, 17),
        'ActiveLearnerResponse': row_value(csv_row, 20, int),
        'AzureCls': row_value(csv_row, 23, int),
        'AzureAmb': row_value(csv_row, 24, int),
        'AzureCFD': row_value(csv_row, 25, float),
        'EmbedCls': row_value(csv_row, 28, float),
        'EmbedCFD': row_value(csv_row, 29, float),
        'Results': row_value(csv_row, 30, float),
    }

    for offset in range(44):
        csv_idx = 31 + offset
        col_name = f'readings{offset}'
        data[col_name] = row_value(csv_row, csv_idx, float)

    return data


def import_test_data():
    parser = argparse.ArgumentParser(
        description='Import Roche WSSVC CSV data into SQLite tables (test_data or all_readings)'
    )
    parser.add_argument('--csv', default='/home/azureuser/code/wssvc-flow-codex/flatten/input/test_wssvc_2025-10-25.csv',
                        help='Path to CSV file to import (default: legacy test dataset)')
    parser.add_argument('--db', default='~/dbs/readings.db',
                        help='Path to SQLite database file (default: ~/dbs/readings.db)')
    parser.add_argument('--table', default='test_data',
                        help='Target table name (default: test_data)')
    parser.add_argument('--recreate-table', action='store_true',
                        help='Drop and recreate the target table (only allowed for test_data)')
    parser.add_argument('--source-label', default='test_data',
                        help='Value to store in source_table column when available (default: test_data)')

    args = parser.parse_args()

    csv_file = Path(args.csv).expanduser()
    db_file = Path(args.db).expanduser()
    table_name = args.table

    if not csv_file.exists():
        print(f"ERROR: CSV file not found: {csv_file}")
        sys.exit(1)

    if not db_file.exists():
        print(f"ERROR: Database not found: {db_file}")
        sys.exit(1)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    ensure_table(cursor, table_name, args.recreate_table)
    available_columns = get_table_columns(cursor, table_name)
    include_source = args.source_label and 'source_table' in [c.lower() for c in available_columns]
    insert_columns = build_insert_columns(available_columns, include_source)

    placeholders = ','.join(['?'] * len(insert_columns))
    insert_sql = f"INSERT INTO {table_name} ({', '.join(insert_columns)}) VALUES ({placeholders})"

    with csv_file.open('r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header:
            print(f"CSV columns: {len(header)}")
            print(f"First few headers: {header[:10]}")

        row_count = 0
        for csv_row in reader:
            row_data = build_row_dict(csv_row)
            if include_source:
                row_data['source_table'] = args.source_label

            insert_values = [row_data.get(col) for col in insert_columns]
            cursor.execute(insert_sql, insert_values)

            row_count += 1
            if row_count % 1000 == 0:
                print(f"Inserted {row_count} rows...")

    conn.commit()
    print("\nImport completed successfully!")
    print(f"Inserted {row_count} rows into {table_name} table")

    cursor.execute("SELECT COUNT(*) FROM readings")
    readings_count = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    target_count = cursor.fetchone()[0]

    print("\nTable counts:")
    print(f"  readings: {readings_count:,}")
    print(f"  {table_name}: {target_count:,}")

    sample_query = f"SELECT Sample, Mix, MixTarget, Type, readings0, readings1 FROM {table_name} LIMIT 3"
    cursor.execute(sample_query)
    sample_rows = cursor.fetchall()
    print(f"\nSample data from {table_name}:")
    for row in sample_rows:
        print(f"  {row}")

    if table_name != 'readings':
        print("\nChecking for potential duplicates with readings table...")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM {table} t
            JOIN readings r ON t.FileUID = r.FileUID
                AND t.Tube = r.Tube
                AND t.Target = r.Target
            """.format(table=table_name)
        )
        duplicate_count = cursor.fetchone()[0]
        print(f"Found {duplicate_count:,} potential duplicates based on (FileUID, Tube, Target)")

    conn.close()


if __name__ == "__main__":
    import_test_data()
