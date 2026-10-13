"""
download_and_compile_mona.py
============================
Automated Downloader and Streaming Compiler for MoNa Experimental Spectra (~1.75M Records).

Downloads: MoNA-export-Experimental_Spectra-msp.zip (~3.07 GB) from UC Davis
Compiles:
  - mona/mona_spectra.parquet (~3.8 GB)
  - mona/unique_smiles_index.parquet
  - mona/mz_index.npz
"""

import os
import sys
import time
import zipfile
import urllib.request
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from mona_manager import (
    DOWNLOADS_DIR,
    PARQUET_FILE,
    SMILES_INDEX_FILE,
    MZ_INDEX_FILE,
    MonaManager,
    mona_manager
)

URL_EXPERIMENTAL = "https://mona.fiehnlab.ucdavis.edu/rest/downloads/retrieve/ab8dc037-14e9-416f-a663-8607d16f3d39"
ZIP_NAME = "MoNA-export-Experimental_Spectra-msp.zip"
TARGET_ZIP = os.path.join(DOWNLOADS_DIR, ZIP_NAME)
PART_ZIP = TARGET_ZIP + ".part"
EXPECTED_SIZE = 3219805004  # ~3.22 GB / 3.00 GiB


def format_bytes(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_time(seconds: float) -> str:
    if seconds < 0 or seconds > 86400 * 7:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


def download_file(url: str, target_path: str, part_path: str, expected_size: int = 0) -> bool:
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # Check if target already fully downloaded and valid
    if os.path.exists(target_path):
        size = os.path.getsize(target_path)
        if (expected_size == 0 or size == expected_size) and zipfile.is_zipfile(target_path):
            print(f"[MoNa Download] Ziel-Archiv existiert bereits und ist valide ({format_bytes(size)}). Überspringe Download.")
            return True
        else:
            print(f"[MoNa Download] Vorhandene Datei unvollständig ({format_bytes(size)}). Starte Neu-Download...")
            try:
                os.remove(target_path)
            except Exception:
                pass

    print(f"[MoNa Download] Starte Download von {url}")
    print(f"[MoNa Download] Ziel: {target_path}")

    headers = {
        "User-Agent": "HGTTD/1.0 (Metabolomics and NMR Research Tool)"
    }
    req = urllib.request.Request(url, headers=headers)

    t_start = time.time()
    t_last_log = t_start
    bytes_downloaded = 0
    chunk_size = 2 * 1024 * 1024  # 2 MB chunks

    try:
        with urllib.request.urlopen(req, timeout=30) as response, open(part_path, "wb") as out_file:
            content_len_hdr = response.headers.get("Content-Length")
            total_size = int(content_len_hdr) if content_len_hdr else expected_size

            print(f"[MoNa Download] Dateigröße vom Server gemeldet: {format_bytes(total_size)}")

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                bytes_downloaded += len(chunk)

                now = time.time()
                if now - t_last_log >= 5.0 or (total_size > 0 and bytes_downloaded >= total_size):
                    elapsed = now - t_start
                    speed = bytes_downloaded / elapsed if elapsed > 0 else 0
                    pct = (bytes_downloaded / total_size * 100.0) if total_size > 0 else 0.0
                    eta = (total_size - bytes_downloaded) / speed if (speed > 0 and total_size > bytes_downloaded) else 0

                    print(
                        f"[MoNa Download] {format_bytes(bytes_downloaded)} / {format_bytes(total_size)} "
                        f"({pct:.1f}%) | {format_bytes(speed)}/s | ETA: {format_time(eta)}"
                    )
                    sys.stdout.flush()
                    t_last_log = now

        # Rename part to final target
        if os.path.exists(target_path):
            os.remove(target_path)
        os.rename(part_path, target_path)

        total_elapsed = time.time() - t_start
        avg_speed = bytes_downloaded / total_elapsed if total_elapsed > 0 else 0
        print(f"[MoNa Download] Download erfolgreich abgeschlossen in {format_time(total_elapsed)} ({format_bytes(avg_speed)}/s).")
        return True

    except Exception as e:
        print(f"[MoNa Download] Fehler beim Download: {e}")
        return False


def main():
    print("=" * 70)
    print("  HGTTD - MassBank of North America (MoNa) All Experimental Downloader")
    print("=" * 70)

    # 1. Download archive
    success = download_file(URL_EXPERIMENTAL, TARGET_ZIP, PART_ZIP, EXPECTED_SIZE)
    if not success:
        print("[MoNa Setup] Download fehlgeschlagen. Abbruch.")
        sys.exit(1)

    # 2. Check zip validity
    print("\n[MoNa Setup] Überprüfe Archiv-Integrität...")
    if not zipfile.is_zipfile(TARGET_ZIP):
        print("[MoNa Setup] FEHLER: Die heruntergeladene Datei ist kein gültiges ZIP-Archiv!")
        sys.exit(1)

    with zipfile.ZipFile(TARGET_ZIP, "r") as zf:
        members = zf.namelist()
        print(f"[MoNa Setup] Archiv-Validierung erfolgreich. Enthaltene Dateien: {members}")

    # 3. Compile database into Parquet
    print("\n[MoNa Setup] Starte Kompilierung der Parquet-Datenbank...")
    t0 = time.time()

    def progress_cb(msg, curr, total):
        print(f"[MoNa Compiler] {msg} ({curr}/{total})")
        sys.stdout.flush()

    try:
        count = mona_manager.build_database_from_downloads(progress_callback=progress_cb)
        dt = time.time() - t0
        print(f"\n[MoNa Setup] ERFOLG! {count:,} Spektren kompiliert in {format_time(dt)}.")
        print(f"[MoNa Setup] Parquet-Größe: {format_bytes(os.path.getsize(PARQUET_FILE))}")
        print(f"[MoNa Setup] SMILES-Index-Größe: {format_bytes(os.path.getsize(SMILES_INDEX_FILE))}")
        print(f"[MoNa Setup] m/z-Index-Größe: {format_bytes(os.path.getsize(MZ_INDEX_FILE))}")
    except Exception as e:
        print(f"\n[MoNa Setup] Fehler beim Kompilieren: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
