#!/usr/bin/env python3

import sqlite3
import argparse
import sys

def get_current_example_ids(conn):
    """Get current example IDs from database"""
    cursor = conn.cursor()
    
    # Check if example_ids table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        return set()
    
    cursor.execute("SELECT id FROM example_ids ORDER BY id")
    return set(row[0] for row in cursor.fetchall())

def create_example_ids_table(conn):
    """Create example_ids table if it doesn't exist"""
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS example_ids (id INTEGER PRIMARY KEY)")
    conn.commit()

def add_example_ids(conn, ids_to_add):
    """Add IDs to example_ids table"""
    cursor = conn.cursor()
    create_example_ids_table(conn)
    
    current_ids = get_current_example_ids(conn)
    added = []
    already_exists = []
    
    for id_val in ids_to_add:
        if id_val in current_ids:
            already_exists.append(id_val)
        else:
            cursor.execute("INSERT INTO example_ids (id) VALUES (?)", (id_val,))
            added.append(id_val)
    
    conn.commit()
    
    return added, already_exists

def remove_example_ids(conn, ids_to_remove):
    """Remove IDs from example_ids table"""
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        return [], ids_to_remove  # All IDs are "not found"
    
    current_ids = get_current_example_ids(conn)
    removed = []
    not_found = []
    
    for id_val in ids_to_remove:
        if id_val in current_ids:
            cursor.execute("DELETE FROM example_ids WHERE id = ?", (id_val,))
            removed.append(id_val)
        else:
            not_found.append(id_val)
    
    conn.commit()
    
    return removed, not_found

def list_example_ids(conn):
    """List all current example IDs"""
    current_ids = get_current_example_ids(conn)
    
    if not current_ids:
        print("No example IDs currently stored in database")
        return
    
    # Sort IDs for display
    sorted_ids = sorted(current_ids)
    
    print(f"Current example IDs ({len(sorted_ids)} total):")
    print("-" * 50)
    
    # Display in rows of 10 for readability
    for i in range(0, len(sorted_ids), 10):
        row = sorted_ids[i:i+10]
        print(" ".join(f"{id:5d}" for id in row))
    
    print("-" * 50)
    print(f"Total: {len(sorted_ids)} IDs")

def validate_ids_exist_in_readings(conn, ids_to_check):
    """Check which IDs exist in the readings table"""
    cursor = conn.cursor()
    existing = []
    missing = []
    
    for id_val in ids_to_check:
        cursor.execute("SELECT 1 FROM readings WHERE id = ? AND in_use = 1", (id_val,))
        if cursor.fetchone():
            existing.append(id_val)
        else:
            missing.append(id_val)
    
    return existing, missing

def main():
    parser = argparse.ArgumentParser(
        description='Manage example IDs in the database',
        epilog='Note: --add and --remove are mutually exclusive'
    )
    
    # Mutually exclusive group for add/remove
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--add', type=str,
                            help='Comma-separated list of IDs to add (e.g., 100,200,300)')
    action_group.add_argument('--remove', type=str,
                            help='Comma-separated list of IDs to remove (e.g., 100,200,300)')
    
    parser.add_argument('--list', action='store_true',
                       help='List all current example IDs')
    parser.add_argument('--db', type=str, default='readings.db',
                       help='Path to SQLite database file (default: readings.db)')
    parser.add_argument('--validate', action='store_true',
                       help='Check if IDs exist in readings table before adding')
    
    # Standard parameters that can't be added to this script (for documentation)
    # can't add: --all (not applicable - specific ID management)
    # can't add: --files (not file-based)
    # can't add: --output (displays to console)
    # can't add: --k, --default-k, --test-k (no CUSUM parameters)
    # can't add: --threshold, --cusum-limit (no thresholds)
    # can't add: --example-dataset (this manages the example dataset)
    # can't add: --limit (operates on specific IDs)
    # can't add: --sort-order, --sort-by (list always sorted by ID)
    
    args = parser.parse_args()
    
    # If no action specified, just list
    if not args.add and not args.remove and not args.list:
        args.list = True
    
    # Connect to database
    try:
        conn = sqlite3.connect(args.db)
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)
    
    try:
        # Handle --add
        if args.add:
            try:
                ids_to_add = [int(x.strip()) for x in args.add.split(',')]
            except ValueError:
                print("Error: Invalid ID format. IDs must be integers separated by commas.")
                sys.exit(1)
            
            # Validate IDs exist in readings table if requested
            if args.validate:
                existing, missing = validate_ids_exist_in_readings(conn, ids_to_add)
                if missing:
                    print(f"Warning: The following IDs do not exist in readings table (in_use=1):")
                    print(f"  {', '.join(map(str, missing))}")
                    print(f"Skipping invalid IDs and adding only the {len(existing)} valid IDs.")
                    ids_to_add = existing
            
            if not ids_to_add:
                print("No valid IDs to add.")
                sys.exit(0)
            
            added, already_exists = add_example_ids(conn, ids_to_add)
            
            if added:
                print(f"Successfully added {len(added)} IDs:")
                print(f"  {', '.join(map(str, sorted(added)))}")
            
            if already_exists:
                print(f"Skipped {len(already_exists)} IDs (already exist):")
                print(f"  {', '.join(map(str, sorted(already_exists)))}")
            
            if not added and not already_exists:
                print("No changes made.")
        
        # Handle --remove
        elif args.remove:
            try:
                ids_to_remove = [int(x.strip()) for x in args.remove.split(',')]
            except ValueError:
                print("Error: Invalid ID format. IDs must be integers separated by commas.")
                sys.exit(1)
            
            removed, not_found = remove_example_ids(conn, ids_to_remove)
            
            if removed:
                print(f"Successfully removed {len(removed)} IDs:")
                print(f"  {', '.join(map(str, sorted(removed)))}")
            
            if not_found:
                print(f"Skipped {len(not_found)} IDs (not found):")
                print(f"  {', '.join(map(str, sorted(not_found)))}")
            
            if not removed and not not_found:
                print("No changes made.")
        
        # Handle --list (or default behavior)
        if args.list:
            list_example_ids(conn)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()