import os
import shutil
from config_manager import (
    get_source_db_path, 
    get_local_sdf_name, 
    get_nmrexp_rel_path
)
from i18n import t

def verify_and_update_db(project_dir=".", progress_callback=None):
    """
    Verifies if the local database is up to date with the configured source version.
    Copies it if it is missing or out of date.
    Maintains a reliable fallback to the local file if the update source is missing,
    ensuring that no crash occurs.
    Returns:
        Absolute path of the database to use, or None if no database exists at all.
    """
    source_path = get_source_db_path()
    local_name = get_local_sdf_name()
    local_path = os.path.join(project_dir, local_name)
    
    # Check if source exists
    source_exists = bool(source_path and os.path.exists(source_path))

    if not source_exists:
        if os.path.exists(local_path):
            if progress_callback:
                progress_callback(t("source_missing_msg", name=local_name))
            return os.path.abspath(local_path)
        else:
            if progress_callback:
                progress_callback(t("no_db_found_msg"))
            return None

    # Determine if we need to copy
    need_copy = False
    if not os.path.exists(local_path):
        need_copy = True
        if progress_callback:
            progress_callback(t("copying_from_source"))
    else:
        try:
            src_stat = os.stat(source_path)
            local_stat = os.stat(local_path)
            
            # Check size and modification time
            if src_stat.st_mtime > local_stat.st_mtime or src_stat.st_size != local_stat.st_size:
                need_copy = True
                if progress_callback:
                    progress_callback(t("db_outdated_copying"))
            else:
                if progress_callback:
                    progress_callback(t("db_up_to_date"))
        except Exception as e:
            print(f"[database_manager] Fehler beim Stat-Vergleich: {e}")
            need_copy = False

    if need_copy:
        try:
            # Using copy2 to preserve metadata (timestamps)
            shutil.copy2(source_path, local_path)
            if progress_callback:
                progress_callback(t("db_sync_success"))
        except Exception as e:
            if progress_callback:
                progress_callback(t("db_sync_warning", err=e))
            # Fallback to local copy if it already existed
            if os.path.exists(local_path):
                return os.path.abspath(local_path)
            else:
                return None

    return os.path.abspath(local_path) if os.path.exists(local_path) else None

def get_nmrexp_path(project_dir="."):
    """Returns absolute path to the configured NMRexp parquet file."""
    rel = get_nmrexp_rel_path()
    if os.path.isabs(rel):
        return rel
    return os.path.abspath(os.path.join(project_dir, rel))

def check_all_databases_status(project_dir="."):
    """
    Checks availability of both nmrshiftdb2 (SDF) and NMRexp (Parquet).
    Returns a dict with status information.
    """
    local_name = get_local_sdf_name()
    sdf_path = os.path.join(project_dir, local_name)
    parquet_path = get_nmrexp_path(project_dir)
    source_path = get_source_db_path()
    
    sdf_exists = os.path.exists(sdf_path)
    parquet_exists = os.path.exists(parquet_path)
    source_exists = bool(source_path and os.path.exists(source_path))
    
    return {
        "sdf_available": sdf_exists,
        "sdf_path": os.path.abspath(sdf_path) if sdf_exists else None,
        "source_available": source_exists,
        "source_path": source_path,
        "parquet_available": parquet_exists,
        "parquet_path": parquet_path if parquet_exists else None,
    }
