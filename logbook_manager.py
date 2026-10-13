import os
import sqlite3
import json
import time
from datetime import datetime

LOGBOOK_DB_NAME = "user_logbook.db"

class LogbookManager:
    """
    Manages user search history, viewed molecules, bookmarks, tags, and notes.
    Persists all data reliably in a local SQLite database (user_logbook.db).
    """
    def __init__(self, db_path=None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, LOGBOOK_DB_NAME)
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Table: Molecules (Bookmarks, favorites, notes)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS molecules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                smiles TEXT NOT NULL,
                name TEXT,
                formula TEXT,
                source_db TEXT,
                nmr_type TEXT,
                record_id TEXT,
                is_favorite INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                first_seen_ts REAL,
                last_seen_ts REAL,
                data_json TEXT DEFAULT ''
            )
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_smiles ON molecules(smiles)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mol_favorite ON molecules(is_favorite)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mol_last_seen ON molecules(last_seen_ts)")

            # Table: History / Activity Log (searches, browsed records)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_type TEXT NOT NULL, -- 'search', 'browse', 'view_3d', 'view_spectrum'
                query_info TEXT,
                smiles TEXT,
                title TEXT,
                timestamp REAL NOT NULL,
                details_json TEXT DEFAULT ''
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_timestamp ON activity_log(timestamp)")
            conn.commit()

    def log_activity(self, activity_type, query_info="", smiles="", title="", details=None):
        """
        Records an action in the activity log.
        """
        now = time.time()
        details_str = json.dumps(details, ensure_ascii=False) if details else ""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO activity_log (activity_type, query_info, smiles, title, timestamp, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (activity_type, query_info, smiles, title, now, details_str))
                conn.commit()
        except Exception as e:
            print(f"[LogbookManager] Fehler beim Protokollieren der Aktivität: {e}")

    def touch_molecule(self, record, mark_favorite=None, notes=None, tags=None):
        """
        Inserts or updates a molecule in the logbook database.
        """
        smiles = record.get("smiles")
        if not smiles:
            return
        now = time.time()
        name = record.get("name") or record.get("filename") or "Unbekannt"
        formula = record.get("formula", "")
        source_db = record.get("source_db", "NMRexp")
        nmr_type = record.get("nmr_type", "NMR")
        rec_id = str(record.get("id") or record.get("row_idx") or "")
        
        # Keep lightweight copy of record
        data_copy = {
            "smiles": smiles,
            "name": name,
            "formula": formula,
            "source_db": source_db,
            "nmr_type": nmr_type,
            "solvent": record.get("solvent", ""),
            "frequency": record.get("frequency", ""),
            "spectrum": record.get("spectrum", []),
            "normalized_peaks": record.get("normalized_peaks", [])[:30] if record.get("normalized_peaks") else []
        }
        data_json = json.dumps(data_copy, ensure_ascii=False)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, is_favorite, notes, tags FROM molecules WHERE smiles = ?", (smiles,))
                row = cursor.fetchone()
                if row:
                    mol_id = row["id"]
                    fav = row["is_favorite"] if mark_favorite is None else (1 if mark_favorite else 0)
                    note_val = row["notes"] if notes is None else notes
                    tag_val = row["tags"] if tags is None else tags
                    cursor.execute("""
                    UPDATE molecules
                    SET last_seen_ts = ?, is_favorite = ?, notes = ?, tags = ?,
                        name = COALESCE(NULLIF(?, ''), name),
                        formula = COALESCE(NULLIF(?, ''), formula),
                        source_db = ?, nmr_type = ?, data_json = ?
                    WHERE id = ?
                    """, (now, fav, note_val, tag_val, name, formula, source_db, nmr_type, data_json, mol_id))
                else:
                    fav = 1 if mark_favorite else 0
                    note_val = notes or ""
                    tag_val = tags or ""
                    cursor.execute("""
                    INSERT INTO molecules (
                        smiles, name, formula, source_db, nmr_type, record_id,
                        is_favorite, notes, tags, first_seen_ts, last_seen_ts, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        smiles, name, formula, source_db, nmr_type, rec_id,
                        fav, note_val, tag_val, now, now, data_json
                    ))
                conn.commit()
        except Exception as e:
            print(f"[LogbookManager] Fehler bei touch_molecule: {e}")

    def toggle_favorite(self, smiles):
        """
        Toggles is_favorite for a given SMILES. Returns new boolean state.
        """
        if not smiles:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, is_favorite FROM molecules WHERE smiles = ?", (smiles,))
                row = cursor.fetchone()
                if row:
                    new_val = 0 if row["is_favorite"] else 1
                    cursor.execute("UPDATE molecules SET is_favorite = ? WHERE id = ?", (new_val, row["id"]))
                    conn.commit()
                    return bool(new_val)
                else:
                    now = time.time()
                    cursor.execute("""
                    INSERT INTO molecules (smiles, is_favorite, first_seen_ts, last_seen_ts)
                    VALUES (?, 1, ?, ?)
                    """, (smiles, now, now))
                    conn.commit()
                    return True
        except Exception as e:
            print(f"[LogbookManager] Fehler bei toggle_favorite: {e}")
            return False

    def is_favorite(self, smiles):
        if not smiles:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_favorite FROM molecules WHERE smiles = ?", (smiles,))
                row = cursor.fetchone()
                return bool(row["is_favorite"]) if row else False
        except Exception:
            return False

    def update_notes_tags(self, smiles, notes=None, tags=None):
        if not smiles:
            return
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                updates = []
                params = []
                if notes is not None:
                    updates.append("notes = ?")
                    params.append(notes)
                if tags is not None:
                    updates.append("tags = ?")
                    params.append(tags)
                if updates:
                    params.append(smiles)
                    query = f"UPDATE molecules SET {', '.join(updates)} WHERE smiles = ?"
                    cursor.execute(query, tuple(params))
                    conn.commit()
        except Exception as e:
            print(f"[LogbookManager] Fehler bei update_notes_tags: {e}")

    def get_molecule_meta(self, smiles):
        if not smiles:
            return None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM molecules WHERE smiles = ?", (smiles,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def get_favorites(self, search_text=""):
        """
        Returns all bookmarked/favorited molecules, optionally filtered by name/SMILES/notes/tags.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if search_text:
                    q = f"%{search_text}%"
                    cursor.execute("""
                    SELECT * FROM molecules
                    WHERE is_favorite = 1 AND (name LIKE ? OR smiles LIKE ? OR notes LIKE ? OR tags LIKE ?)
                    ORDER BY last_seen_ts DESC
                    """, (q, q, q, q))
                else:
                    cursor.execute("""
                    SELECT * FROM molecules
                    WHERE is_favorite = 1
                    ORDER BY last_seen_ts DESC
                    """)
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"[LogbookManager] Fehler bei get_favorites: {e}")
            return []

    def get_recent_molecules(self, limit=50):
        """
        Returns recently viewed molecules.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT * FROM molecules
                ORDER BY last_seen_ts DESC
                LIMIT ?
                """, (limit,))
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"[LogbookManager] Fehler bei get_recent_molecules: {e}")
            return []

    def get_recent_activities(self, limit=50):
        """
        Returns recent search and browsing activity.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT * FROM activity_log
                ORDER BY timestamp DESC
                LIMIT ?
                """, (limit,))
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"[LogbookManager] Fehler bei get_recent_activities: {e}")
            return []

    def clear_history(self):
        """
        Clears activity history while keeping bookmarked molecules.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM activity_log")
                cursor.execute("DELETE FROM molecules WHERE is_favorite = 0")
                conn.commit()
                return True
        except Exception as e:
            print(f"[LogbookManager] Fehler bei clear_history: {e}")
            return False

# Global singleton instance
logbook_manager = LogbookManager()
