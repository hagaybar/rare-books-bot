"""Database backup and restore utility.

Automatically backs up bibliographic.db before destructive operations.

Usage:
    python -m scripts.utils.db_backup backup data/index/bibliographic.db
    python -m scripts.utils.db_backup restore data/index/bibliographic.db
"""
import shutil
import sys
from pathlib import Path


def backup_db(db_path: str | Path) -> Path:
    """Copy db_path to db_path.bak. Returns the backup path."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"No database to back up at {db_path}")
        return None
    bak_path = db_path.with_suffix(".db.bak")
    shutil.copy2(db_path, bak_path)
    size_mb = bak_path.stat().st_size / 1024 / 1024
    print(f"Backed up {db_path} -> {bak_path} ({size_mb:.1f} MB)")
    return bak_path


def restore_db(db_path: str | Path) -> bool:
    """Restore db_path from db_path.bak."""
    db_path = Path(db_path)
    bak_path = db_path.with_suffix(".db.bak")
    if not bak_path.exists():
        print(f"No backup found at {bak_path}")
        return False
    shutil.copy2(bak_path, db_path)
    size_mb = db_path.stat().st_size / 1024 / 1024
    print(f"Restored {bak_path} -> {db_path} ({size_mb:.1f} MB)")
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.utils.db_backup <backup|restore> <db_path>")
        sys.exit(1)
    action = sys.argv[1]
    db_path = sys.argv[2]
    if action == "backup":
        backup_db(db_path)
    elif action == "restore":
        restore_db(db_path)
    else:
        print(f"Unknown action: {action}. Use 'backup' or 'restore'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
