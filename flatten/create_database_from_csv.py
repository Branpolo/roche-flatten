#!/usr/bin/env python3

import csv
import sqlite3
import sys
import os

def create_database():
    csv_file = '/home/azureuser/code/wssvc-flow/data-4thAug2025-for_neg_filter.csv'
    db_file = os.path.expanduser('~/dbs/readings.db')
    
    # Remove existing database
    if os.path.exists(db_file):
        os.remove(db_file)
    
    # Connect to SQLite
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Create table with schema based on manual analysis
    create_table_sql = '''
    CREATE TABLE readings (
        Sample TEXT,
        File TEXT,
        FileUID TEXT,
        Extension TEXT,
        Parser TEXT,
        Mix TEXT,
        MixTarget_Full TEXT,  -- Mix:Target column
        MixTarget TEXT,
        MixDetector TEXT,
        Group_Name TEXT,      -- Group column
        Target TEXT,
        Detector TEXT,
        Type TEXT,
        Role TEXT,
        Tube TEXT,
        ActiveLearnerResponse INTEGER,
        AzureCls INTEGER,
        AzureAmb INTEGER,
        AzureCFD REAL,
        EmbedCls REAL,        -- Embed.Cls
        EmbedCFD REAL,        -- Embed.CFD
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
    
    cursor.execute(create_table_sql)
    
    # Read and insert data
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        row_count = 0
        for row in reader:
            # Extract only the columns with data, mapping to our schema
            # Columns: 0=Sample, 1=File, 2=FileUID, 3=Extension, 4=Parser, 5=Mix, 
            #         6=Mix:Target, 7=MixTarget, 8=MixDetector, 10=Group, 11=Target, 
            #         12=Detector, 15=Type, 16=Role, 17=Tube, 20=ActiveLearnerResponse,
            #         23=AzureCls, 24=AzureAmb, 25=AzureCFD, 28=Embed.Cls, 29=Embed.CFD,
            #         31=Results, 32-75=readings0-43
            
            values = [
                row[0] if len(row) > 0 else None,   # Sample
                row[1] if len(row) > 1 else None,   # File
                row[2] if len(row) > 2 else None,   # FileUID
                row[3] if len(row) > 3 else None,   # Extension
                row[4] if len(row) > 4 else None,   # Parser
                row[5] if len(row) > 5 else None,   # Mix
                row[6] if len(row) > 6 else None,   # Mix:Target
                row[7] if len(row) > 7 else None,   # MixTarget
                row[8] if len(row) > 8 else None,   # MixDetector
                row[10] if len(row) > 10 else None, # Group
                row[11] if len(row) > 11 else None, # Target
                row[12] if len(row) > 12 else None, # Detector
                row[15] if len(row) > 15 else None, # Type
                row[16] if len(row) > 16 else None, # Role
                row[17] if len(row) > 17 else None, # Tube
                int(row[20]) if len(row) > 20 and row[20].strip() else None, # ActiveLearnerResponse
                int(row[23]) if len(row) > 23 and row[23].strip() else None, # AzureCls
                int(row[24]) if len(row) > 24 and row[24].strip() else None, # AzureAmb
                float(row[25]) if len(row) > 25 and row[25].strip() else None, # AzureCFD
                float(row[28]) if len(row) > 28 and row[28].strip() else None, # Embed.Cls
                float(row[29]) if len(row) > 29 and row[29].strip() else None, # Embed.CFD
                float(row[31]) if len(row) > 31 and row[31].strip() else None, # Results
            ]
            
            # Add readings columns (32-75 = readings0-43)
            for i in range(32, 76):
                if len(row) > i and row[i].strip():
                    values.append(float(row[i]))
                else:
                    values.append(None)
            
            placeholders = ','.join(['?' for _ in values])
            cursor.execute(f'INSERT INTO readings VALUES ({placeholders})', values)
            
            row_count += 1
            if row_count % 1000 == 0:
                print(f"Inserted {row_count} rows...")
    
    conn.commit()
    print(f"Database created successfully with {row_count} rows")
    print(f"Database file: {db_file}")
    
    # Show sample data
    cursor.execute("SELECT COUNT(*) FROM readings")
    total_rows = cursor.fetchone()[0]
    print(f"Total rows in database: {total_rows}")
    
    cursor.execute("SELECT Sample, Mix, MixTarget, Type, readings0, readings1, readings2 FROM readings LIMIT 3")
    sample_rows = cursor.fetchall()
    print("\nSample data:")
    for row in sample_rows:
        print(row)
    
    conn.close()

if __name__ == "__main__":
    create_database()