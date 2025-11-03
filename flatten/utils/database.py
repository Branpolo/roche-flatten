"""
Database utility functions for the wssvc-flow toolset
"""
import sqlite3
import struct

def bytes_to_float(value):
    """Convert bytes to float if needed, otherwise return as-is"""
    if isinstance(value, bytes):
        return struct.unpack('d', value)[0]
    return value

def get_readings_for_id(conn, target_id, table='readings', num_readings=44):
    """Get readings for a specific ID from the database
    
    Args:
        conn: Database connection
        target_id: ID to fetch
        table: Table name (default 'readings' for WSSVC, use 'qst_readings' for QST)
        num_readings: Number of reading columns (44 for WSSVC, 50 for QST)
    """
    cursor = conn.cursor()
    readings_columns = [f"readings{i}" for i in range(num_readings)]
    readings_select = ", ".join(readings_columns)
    cursor.execute(f"SELECT {readings_select} FROM {table} WHERE id = ?", (target_id,))
    row = cursor.fetchone()
    if not row:
        return []
    readings = [r for r in row if r is not None]
    return readings

def get_example_ids(conn, sort_order='down'):
    """Get example IDs from database"""
    cursor = conn.cursor()
    
    # First check if example_ids table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        print("Creating example_ids table...")
        cursor.execute("CREATE TABLE example_ids (id INTEGER PRIMARY KEY)")
        
        # Insert the example IDs from feedback plots + 2112 (key test case)
        example_ids = [3, 8, 9, 10, 20, 30, 33, 38, 49, 59, 60, 199, 203, 206, 367, 386, 
                      427, 434, 479, 486, 600, 601, 820, 1256, 1264, 1276, 1339, 1340, 
                      1782, 1825, 1862, 1877, 2112, 2300, 2304]
        
        for example_id in example_ids:
            cursor.execute("INSERT INTO example_ids (id) VALUES (?)", (example_id,))
        
        conn.commit()
        print(f"Populated example_ids table with {len(example_ids)} IDs")
    
    # Get example IDs that exist in the readings table
    cursor.execute("""
    SELECT e.id
    FROM example_ids e
    JOIN readings r ON e.id = r.id
    WHERE r.in_use = 1
    """)
    
    return [row[0] for row in cursor.fetchall()]

def get_example_ids_with_cusum(conn, sort_order='down'):
    """Get example IDs with CUSUM values from database"""
    cursor = conn.cursor()
    
    # First check if example_ids table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        create_example_ids_table(conn, [3, 8, 9, 10, 20, 30, 33, 38, 49, 59, 60, 199, 203, 206, 367, 386, 
                      427, 434, 479, 486, 600, 601, 820, 1256, 1264, 1276, 1339, 1340, 
                      1782, 1825, 1862, 1877, 2112, 2300, 2304])
    
    # Get example IDs with CUSUM values
    if sort_order == 'none':
        # No sorting - just return in whatever order
        cursor.execute("""
        SELECT e.id, r.cusum_min_correct
        FROM example_ids e
        JOIN readings r ON e.id = r.id
        WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
        """)
    else:
        # Sort by database CUSUM values
        order_sql = "DESC" if sort_order == 'down' else "ASC"
        cursor.execute(f"""
        SELECT e.id, r.cusum_min_correct
        FROM example_ids e
        JOIN readings r ON e.id = r.id
        WHERE r.in_use = 1 AND r.cusum_min_correct IS NOT NULL
        ORDER BY r.cusum_min_correct {order_sql}
        """)
    
    # Convert bytes to float for cusum_min_correct
    return [(id, bytes_to_float(cusum_min)) for id, cusum_min in cursor.fetchall()]

def create_example_ids_table(conn, ids_list):
    """Create and populate example_ids table"""
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS example_ids (id INTEGER PRIMARY KEY)")
    
    for example_id in ids_list:
        cursor.execute("INSERT OR IGNORE INTO example_ids (id) VALUES (?)", (example_id,))
    
    conn.commit()
    return len(ids_list)