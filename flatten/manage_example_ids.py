#!/usr/bin/env python3

import sqlite3
import argparse
import sys

def get_current_example_ids(conn):
    """Get current example IDs with mix/target from database"""
    cursor = conn.cursor()

    # Check if example_ids table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        return {}

    # Check if mix/target columns exist (for backward compatibility)
    cursor.execute("PRAGMA table_info(example_ids)")
    columns = [row[1] for row in cursor.fetchall()]
    has_mix_target = 'mix' in columns and 'target' in columns

    if has_mix_target:
        cursor.execute("SELECT id, mix, target FROM example_ids ORDER BY id")
        # Return dict: {id: (mix, target)}
        return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    else:
        cursor.execute("SELECT id FROM example_ids ORDER BY id")
        # Return dict: {id: (None, None)} for backward compatibility
        return {row[0]: (None, None) for row in cursor.fetchall()}

def create_example_ids_table(conn):
    """Create example_ids table if it doesn't exist"""
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS example_ids (id INTEGER PRIMARY KEY, mix TEXT NULL, target TEXT NULL)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_example_ids_mix_target ON example_ids(id, mix, target)")
    conn.commit()

def add_example_ids(conn, ids_to_add):
    """
    Add IDs to example_ids table.

    Args:
        conn: Database connection
        ids_to_add: List of either integers (just ID) or tuples (id, mix, target)

    Returns:
        Tuple of (added_list, already_exists_list)
    """
    cursor = conn.cursor()
    create_example_ids_table(conn)

    current_ids = get_current_example_ids(conn)
    added = []
    already_exists = []

    for item in ids_to_add:
        # Handle both int and tuple formats
        if isinstance(item, tuple):
            id_val, mix_val, target_val = item
        else:
            id_val, mix_val, target_val = item, None, None

        # Check if this exact combination exists
        if id_val in current_ids:
            existing_mix, existing_target = current_ids[id_val]
            # If exact match (including mix/target), skip
            if (existing_mix, existing_target) == (mix_val, target_val):
                already_exists.append((id_val, mix_val, target_val))
                continue
            # If ID exists but different mix/target, we need to handle this case
            # For now, we'll treat it as "already exists" to prevent duplicates
            # (SQLite won't allow duplicate PRIMARY KEY anyway)
            already_exists.append((id_val, mix_val, target_val))
        else:
            cursor.execute("INSERT INTO example_ids (id, mix, target) VALUES (?, ?, ?)",
                          (id_val, mix_val, target_val))
            added.append((id_val, mix_val, target_val))

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
    """List all current example IDs with mix/target if present"""
    current_ids = get_current_example_ids(conn)

    if not current_ids:
        print("No example IDs currently stored in database")
        return

    # Sort IDs for display
    sorted_ids = sorted(current_ids.keys())

    # Check if any IDs have mix/target set
    has_mix_target = any(mix is not None or target is not None
                         for mix, target in current_ids.values())

    print(f"Current example IDs ({len(sorted_ids)} total):")
    print("-" * 80)

    if has_mix_target:
        # Display with mix/target columns
        print(f"{'ID':>5}  {'Mix':<10}  {'Target':<20}")
        print("-" * 80)
        for id_val in sorted_ids:
            mix_val, target_val = current_ids[id_val]
            mix_str = mix_val if mix_val else "-"
            target_str = target_val if target_val else "-"
            print(f"{id_val:5d}  {mix_str:<10}  {target_str:<20}")
    else:
        # Display in compact rows of 10 (backward compatible)
        for i in range(0, len(sorted_ids), 10):
            row = sorted_ids[i:i+10]
            print(" ".join(f"{id:5d}" for id in row))

    print("-" * 80)
    print(f"Total: {len(sorted_ids)} IDs")

def update_example_ids(conn, ids_to_update):
    """
    Update mix/target for existing IDs in example_ids table.

    Args:
        conn: Database connection
        ids_to_update: List of tuples (id, mix, target)

    Returns:
        Tuple of (updated_list, not_found_list)
    """
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='example_ids'")
    if not cursor.fetchone():
        return [], ids_to_update  # All IDs are "not found"

    current_ids = get_current_example_ids(conn)
    updated = []
    not_found = []

    for item in ids_to_update:
        if isinstance(item, tuple):
            id_val, mix_val, target_val = item
        else:
            id_val, mix_val, target_val = item, None, None

        if id_val in current_ids:
            cursor.execute("UPDATE example_ids SET mix = ?, target = ? WHERE id = ?",
                          (mix_val, target_val, id_val))
            updated.append((id_val, mix_val, target_val))
        else:
            not_found.append((id_val, mix_val, target_val))

    conn.commit()

    return updated, not_found

def parse_id_spec(spec_string):
    """
    Parse ID specification string into list of tuples.

    Supports formats:
    - "100" -> (100, None, None)
    - "100:ENT:Rubella" -> (100, "ENT", "Rubella")
    - "100,200:RUM:Measles,300" -> [(100, None, None), (200, "RUM", "Measles"), (300, None, None)]

    Args:
        spec_string: Comma-separated list of ID specifications

    Returns:
        List of tuples (id, mix, target)
    """
    results = []
    items = [x.strip() for x in spec_string.split(',')]

    for item in items:
        if ':' in item:
            # Format: id:mix:target
            parts = item.split(':')
            if len(parts) != 3:
                raise ValueError(f"Invalid format '{item}'. Expected 'id:mix:target' or just 'id'")
            try:
                id_val = int(parts[0].strip())
                mix_val = parts[1].strip() if parts[1].strip() else None
                target_val = parts[2].strip() if parts[2].strip() else None
                results.append((id_val, mix_val, target_val))
            except ValueError:
                raise ValueError(f"Invalid ID in '{item}'. ID must be an integer")
        else:
            # Format: just id
            try:
                id_val = int(item)
                results.append((id_val, None, None))
            except ValueError:
                raise ValueError(f"Invalid ID '{item}'. ID must be an integer")

    return results

def validate_ids_exist_in_readings(conn, ids_to_check):
    """
    Check which IDs (and mix/target combinations) exist in the all_readings table.

    Args:
        conn: Database connection
        ids_to_check: List of tuples (id, mix, target) or just integers

    Returns:
        Tuple of (existing_list, missing_list)
    """
    cursor = conn.cursor()
    existing = []
    missing = []

    for item in ids_to_check:
        # Handle both int and tuple formats
        if isinstance(item, tuple):
            id_val, mix_val, target_val = item
        else:
            id_val, mix_val, target_val = item, None, None

        # Build query based on whether mix/target specified
        if mix_val is None and target_val is None:
            # Just check ID exists
            cursor.execute("SELECT 1 FROM all_readings WHERE id = ? AND in_use = 1 LIMIT 1", (id_val,))
        elif mix_val is not None and target_val is None:
            # Check ID and Mix
            cursor.execute("SELECT 1 FROM all_readings WHERE id = ? AND Mix = ? AND in_use = 1 LIMIT 1",
                          (id_val, mix_val))
        elif mix_val is None and target_val is not None:
            # Check ID and MixTarget
            cursor.execute("SELECT 1 FROM all_readings WHERE id = ? AND MixTarget = ? AND in_use = 1 LIMIT 1",
                          (id_val, target_val))
        else:
            # Check ID, Mix, and MixTarget
            cursor.execute("""
                SELECT 1 FROM all_readings
                WHERE id = ? AND Mix = ? AND MixTarget = ? AND in_use = 1
                LIMIT 1
            """, (id_val, mix_val, target_val))

        if cursor.fetchone():
            existing.append((id_val, mix_val, target_val))
        else:
            missing.append((id_val, mix_val, target_val))

    return existing, missing

def main():
    parser = argparse.ArgumentParser(
        description='Manage example IDs in the database',
        epilog='Note: --add and --remove are mutually exclusive'
    )
    
    # Mutually exclusive group for add/remove/update
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--add', type=str,
                            help='Comma-separated list of IDs to add. Formats: "100,200,300" or "100:ENT:Rubella,200:RUM:Measles,300"')
    action_group.add_argument('--remove', type=str,
                            help='Comma-separated list of IDs to remove (e.g., 100,200,300)')
    action_group.add_argument('--update', type=str,
                            help='Update mix/target for existing IDs. Format: "100:ENT:Ent,200:RUM:Measles"')
    
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
    if not args.add and not args.remove and not args.update and not args.list:
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
                ids_to_add = parse_id_spec(args.add)
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

            # Validate IDs exist in readings table if requested
            if args.validate:
                existing, missing = validate_ids_exist_in_readings(conn, ids_to_add)
                if missing:
                    print(f"Warning: The following ID/mix/target combinations do not exist in all_readings table (in_use=1):")
                    for id_val, mix_val, target_val in missing:
                        mix_str = mix_val if mix_val else "-"
                        target_str = target_val if target_val else "-"
                        print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")
                    print(f"Skipping invalid combinations and adding only the {len(existing)} valid ones.")
                    ids_to_add = existing

            if not ids_to_add:
                print("No valid IDs to add.")
                sys.exit(0)

            added, already_exists = add_example_ids(conn, ids_to_add)

            if added:
                print(f"Successfully added {len(added)} ID(s):")
                for id_val, mix_val, target_val in added:
                    if mix_val or target_val:
                        mix_str = mix_val if mix_val else "-"
                        target_str = target_val if target_val else "-"
                        print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")
                    else:
                        print(f"  ID {id_val}")

            if already_exists:
                print(f"Skipped {len(already_exists)} ID(s) (already exist):")
                for id_val, mix_val, target_val in already_exists:
                    if mix_val or target_val:
                        mix_str = mix_val if mix_val else "-"
                        target_str = target_val if target_val else "-"
                        print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")
                    else:
                        print(f"  ID {id_val}")

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

        # Handle --update
        elif args.update:
            try:
                ids_to_update = parse_id_spec(args.update)
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

            # Validate IDs exist in readings table if requested
            if args.validate:
                existing, missing = validate_ids_exist_in_readings(conn, ids_to_update)
                if missing:
                    print(f"Warning: The following ID/mix/target combinations do not exist in all_readings table (in_use=1):")
                    for id_val, mix_val, target_val in missing:
                        mix_str = mix_val if mix_val else "-"
                        target_str = target_val if target_val else "-"
                        print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")
                    print(f"Skipping invalid combinations and updating only the {len(existing)} valid ones.")
                    ids_to_update = existing

            if not ids_to_update:
                print("No valid IDs to update.")
                sys.exit(0)

            updated, not_found = update_example_ids(conn, ids_to_update)

            if updated:
                print(f"Successfully updated {len(updated)} ID(s):")
                for id_val, mix_val, target_val in updated:
                    mix_str = mix_val if mix_val else "-"
                    target_str = target_val if target_val else "-"
                    print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")

            if not_found:
                print(f"Skipped {len(not_found)} ID(s) (not in example_ids table):")
                for id_val, mix_val, target_val in not_found:
                    mix_str = mix_val if mix_val else "-"
                    target_str = target_val if target_val else "-"
                    print(f"  ID {id_val}, Mix: {mix_str}, Target: {target_str}")

            if not updated and not not_found:
                print("No changes made.")

        # Handle --list (or default behavior)
        if args.list:
            list_example_ids(conn)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()