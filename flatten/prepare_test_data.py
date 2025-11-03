#!/usr/bin/env python3
"""
Prepare test_data table by adding required columns for CUSUM processing.
"""

import sqlite3
import sys

def prepare_test_data():
    db_file = '/home/azureuser/code/wssvc-flow/readings.db'

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    print("Adding required columns to test_data...")

    # Start with a fresh copy - recreate test_data with all columns
    # First, save the existing data
    cursor.execute("CREATE TEMP TABLE test_data_backup AS SELECT * FROM test_data")
    cursor.execute("DROP TABLE test_data")

    # Create test_data with full schema matching readings
    cursor.execute("""
    CREATE TABLE test_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        readings43 REAL,
        negative_initial_slope INT,
        in_use INT DEFAULT 1,
        EmbedCT REAL,
        EmbedRFU REAL,
        validation_status TEXT,
        validation_notes TEXT,
        end_of_downward_slope_reading INT,
        cusum0 REAL, cusum1 REAL, cusum2 REAL, cusum3 REAL, cusum4 REAL,
        cusum5 REAL, cusum6 REAL, cusum7 REAL, cusum8 REAL, cusum9 REAL,
        cusum10 REAL, cusum11 REAL, cusum12 REAL, cusum13 REAL, cusum14 REAL,
        cusum15 REAL, cusum16 REAL, cusum17 REAL, cusum18 REAL, cusum19 REAL,
        cusum20 REAL, cusum21 REAL, cusum22 REAL, cusum23 REAL, cusum24 REAL,
        cusum25 REAL, cusum26 REAL, cusum27 REAL, cusum28 REAL, cusum29 REAL,
        cusum30 REAL, cusum31 REAL, cusum32 REAL, cusum33 REAL, cusum34 REAL,
        cusum35 REAL, cusum36 REAL, cusum37 REAL, cusum38 REAL, cusum39 REAL,
        cusum40 REAL, cusum41 REAL, cusum42 REAL, cusum43 REAL,
        cusum_min REAL,
        cusum_negative_slope INT,
        cusum_min_correct REAL,
        cusum_negative_slope_correct INT
    )
    """)

    # Copy data back (id will be auto-generated)
    cursor.execute("""
    INSERT INTO test_data (
        Sample, File, FileUID, Extension, Parser, Mix, MixTarget_Full, MixTarget,
        MixDetector, Group_Name, Target, Detector, Type, Role, Tube,
        ActiveLearnerResponse, AzureCls, AzureAmb, AzureCFD, EmbedCls, EmbedCFD, Results,
        readings0, readings1, readings2, readings3, readings4, readings5, readings6, readings7, readings8, readings9,
        readings10, readings11, readings12, readings13, readings14, readings15, readings16, readings17, readings18, readings19,
        readings20, readings21, readings22, readings23, readings24, readings25, readings26, readings27, readings28, readings29,
        readings30, readings31, readings32, readings33, readings34, readings35, readings36, readings37, readings38, readings39,
        readings40, readings41, readings42, readings43, in_use
    )
    SELECT
        Sample, File, FileUID, Extension, Parser, Mix, MixTarget_Full, MixTarget,
        MixDetector, Group_Name, Target, Detector, Type, Role, Tube,
        ActiveLearnerResponse, AzureCls, AzureAmb, AzureCFD, EmbedCls, EmbedCFD, Results,
        readings0, readings1, readings2, readings3, readings4, readings5, readings6, readings7, readings8, readings9,
        readings10, readings11, readings12, readings13, readings14, readings15, readings16, readings17, readings18, readings19,
        readings20, readings21, readings22, readings23, readings24, readings25, readings26, readings27, readings28, readings29,
        readings30, readings31, readings32, readings33, readings34, readings35, readings36, readings37, readings38, readings39,
        readings40, readings41, readings42, readings43, 1 as in_use
    FROM test_data_backup
    """)

    # Drop temp table
    cursor.execute("DROP TABLE test_data_backup")

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM test_data")
    count = cursor.fetchone()[0]
    print(f"✅ test_data table prepared with {count} records")

    cursor.execute("SELECT MIN(id), MAX(id) FROM test_data")
    min_id, max_id = cursor.fetchone()
    print(f"   ID range: {min_id} to {max_id}")

    conn.close()

if __name__ == "__main__":
    prepare_test_data()
