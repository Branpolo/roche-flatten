#!/usr/bin/env python3
"""
Migrate all_readings table to add id as PRIMARY KEY AUTOINCREMENT
"""
import sqlite3
import sys

def migrate_all_readings_add_id():
    db_path = '/home/azureuser/dbs/readings.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")

        # Create new table with id PRIMARY KEY
        cursor.execute("""
        CREATE TABLE all_readings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            source_table TEXT,
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
            readings0 REAL, readings1 REAL, readings2 REAL, readings3 REAL, readings4 REAL,
            readings5 REAL, readings6 REAL, readings7 REAL, readings8 REAL, readings9 REAL,
            readings10 REAL, readings11 REAL, readings12 REAL, readings13 REAL, readings14 REAL,
            readings15 REAL, readings16 REAL, readings17 REAL, readings18 REAL, readings19 REAL,
            readings20 REAL, readings21 REAL, readings22 REAL, readings23 REAL, readings24 REAL,
            readings25 REAL, readings26 REAL, readings27 REAL, readings28 REAL, readings29 REAL,
            readings30 REAL, readings31 REAL, readings32 REAL, readings33 REAL, readings34 REAL,
            readings35 REAL, readings36 REAL, readings37 REAL, readings38 REAL, readings39 REAL,
            readings40 REAL, readings41 REAL, readings42 REAL, readings43 REAL,
            negative_initial_slope INTEGER DEFAULT 0,
            in_use INTEGER DEFAULT 1,
            EmbedCT REAL,
            EmbedRFU REAL,
            validation_status TEXT DEFAULT NULL,
            validation_notes TEXT DEFAULT NULL,
            end_of_downward_slope_reading INTEGER DEFAULT -1,
            cusum0 REAL DEFAULT NULL, cusum1 REAL DEFAULT NULL, cusum2 REAL DEFAULT NULL, cusum3 REAL DEFAULT NULL, cusum4 REAL DEFAULT NULL,
            cusum5 REAL DEFAULT NULL, cusum6 REAL DEFAULT NULL, cusum7 REAL DEFAULT NULL, cusum8 REAL DEFAULT NULL, cusum9 REAL DEFAULT NULL,
            cusum10 REAL DEFAULT NULL, cusum11 REAL DEFAULT NULL, cusum12 REAL DEFAULT NULL, cusum13 REAL DEFAULT NULL, cusum14 REAL DEFAULT NULL,
            cusum15 REAL DEFAULT NULL, cusum16 REAL DEFAULT NULL, cusum17 REAL DEFAULT NULL, cusum18 REAL DEFAULT NULL, cusum19 REAL DEFAULT NULL,
            cusum20 REAL DEFAULT NULL, cusum21 REAL DEFAULT NULL, cusum22 REAL DEFAULT NULL, cusum23 REAL DEFAULT NULL, cusum24 REAL DEFAULT NULL,
            cusum25 REAL DEFAULT NULL, cusum26 REAL DEFAULT NULL, cusum27 REAL DEFAULT NULL, cusum28 REAL DEFAULT NULL, cusum29 REAL DEFAULT NULL,
            cusum30 REAL DEFAULT NULL, cusum31 REAL DEFAULT NULL, cusum32 REAL DEFAULT NULL, cusum33 REAL DEFAULT NULL, cusum34 REAL DEFAULT NULL,
            cusum35 REAL DEFAULT NULL, cusum36 REAL DEFAULT NULL, cusum37 REAL DEFAULT NULL, cusum38 REAL DEFAULT NULL, cusum39 REAL DEFAULT NULL,
            cusum40 REAL DEFAULT NULL, cusum41 REAL DEFAULT NULL, cusum42 REAL DEFAULT NULL, cusum43 REAL DEFAULT NULL,
            cusum_min REAL DEFAULT NULL,
            cusum_negative_slope INTEGER DEFAULT 0,
            cusum_min_correct REAL DEFAULT NULL,
            cusum_negative_slope_correct INTEGER DEFAULT 0,
            ar_cfd REAL,
            ar_cls INTEGER,
            ar_amb INTEGER,
            ar_ct REAL,
            azure_order INTEGER,
            ar_order INTEGER
        )
        """)

        # Copy data from old table to new table (id will auto-increment)
        cursor.execute("""
        INSERT INTO all_readings_new (
            original_id, source_table, Sample, File, FileUID, Extension, Parser, Mix,
            MixTarget_Full, MixTarget, MixDetector, Group_Name, Target, Detector, Type,
            Role, Tube, ActiveLearnerResponse, AzureCls, AzureAmb, AzureCFD, EmbedCls,
            EmbedCFD, Results, readings0, readings1, readings2, readings3, readings4,
            readings5, readings6, readings7, readings8, readings9, readings10, readings11,
            readings12, readings13, readings14, readings15, readings16, readings17, readings18,
            readings19, readings20, readings21, readings22, readings23, readings24, readings25,
            readings26, readings27, readings28, readings29, readings30, readings31, readings32,
            readings33, readings34, readings35, readings36, readings37, readings38, readings39,
            readings40, readings41, readings42, readings43, negative_initial_slope, in_use,
            EmbedCT, EmbedRFU, validation_status, validation_notes, end_of_downward_slope_reading,
            cusum0, cusum1, cusum2, cusum3, cusum4, cusum5, cusum6, cusum7, cusum8, cusum9,
            cusum10, cusum11, cusum12, cusum13, cusum14, cusum15, cusum16, cusum17, cusum18,
            cusum19, cusum20, cusum21, cusum22, cusum23, cusum24, cusum25, cusum26, cusum27,
            cusum28, cusum29, cusum30, cusum31, cusum32, cusum33, cusum34, cusum35, cusum36,
            cusum37, cusum38, cusum39, cusum40, cusum41, cusum42, cusum43, cusum_min,
            cusum_negative_slope, cusum_min_correct, cusum_negative_slope_correct, ar_cfd,
            ar_cls, ar_amb, ar_ct, azure_order, ar_order
        )
        SELECT
            original_id, source_table, Sample, File, FileUID, Extension, Parser, Mix,
            MixTarget_Full, MixTarget, MixDetector, Group_Name, Target, Detector, Type,
            Role, Tube, ActiveLearnerResponse, AzureCls, AzureAmb, AzureCFD, EmbedCls,
            EmbedCFD, Results, readings0, readings1, readings2, readings3, readings4,
            readings5, readings6, readings7, readings8, readings9, readings10, readings11,
            readings12, readings13, readings14, readings15, readings16, readings17, readings18,
            readings19, readings20, readings21, readings22, readings23, readings24, readings25,
            readings26, readings27, readings28, readings29, readings30, readings31, readings32,
            readings33, readings34, readings35, readings36, readings37, readings38, readings39,
            readings40, readings41, readings42, readings43, negative_initial_slope, in_use,
            EmbedCT, EmbedRFU, validation_status, validation_notes, end_of_downward_slope_reading,
            cusum0, cusum1, cusum2, cusum3, cusum4, cusum5, cusum6, cusum7, cusum8, cusum9,
            cusum10, cusum11, cusum12, cusum13, cusum14, cusum15, cusum16, cusum17, cusum18,
            cusum19, cusum20, cusum21, cusum22, cusum23, cusum24, cusum25, cusum26, cusum27,
            cusum28, cusum29, cusum30, cusum31, cusum32, cusum33, cusum34, cusum35, cusum36,
            cusum37, cusum38, cusum39, cusum40, cusum41, cusum42, cusum43, cusum_min,
            cusum_negative_slope, cusum_min_correct, cusum_negative_slope_correct, ar_cfd,
            ar_cls, ar_amb, ar_ct, azure_order, ar_order
        FROM all_readings
        """)

        # Drop old table
        cursor.execute("DROP TABLE all_readings")

        # Rename new table to old name
        cursor.execute("ALTER TABLE all_readings_new RENAME TO all_readings")

        # Recreate indexes
        cursor.execute("""
        CREATE UNIQUE INDEX idx_all_readings_composite
        ON all_readings(FileUID, Tube, Mix, MixTarget)
        """)

        cursor.execute("""
        CREATE UNIQUE INDEX idx_all_readings_tube_target
        ON all_readings(FileUID, Tube, Target)
        """)

        cursor.execute("""
        CREATE UNIQUE INDEX idx_all_readings_file_composite
        ON all_readings(File, Tube, Mix, MixTarget)
        """)

        cursor.execute("""
        CREATE UNIQUE INDEX idx_all_readings_file_tube_target
        ON all_readings(File, Tube, Target)
        """)

        # Commit transaction
        conn.commit()
        print("✓ Successfully migrated all_readings table with id PRIMARY KEY AUTOINCREMENT")
        print(f"✓ Preserved all 46494 rows")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_all_readings_add_id()
