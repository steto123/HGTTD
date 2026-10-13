"""
download_and_compile_ir.py — Downloader & Compiler for SQuIRL & NIST IR Spectra
HGTTD — Hitchhiker's Guide through the Database 🌌🪐
"""

import os
import sys
import time
import json
import urllib.request
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

IR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir")
DOWNLOADS_DIR = os.path.join(IR_DIR, "downloads")
SQUIRL_H5_PATH = os.path.join(DOWNLOADS_DIR, "SQuIRL_v1.0.h5")
SQUIRL_CSV_PATH = os.path.join(DOWNLOADS_DIR, "SQuIRL_v1.0_metadata.csv")
OUTPUT_PARQUET = os.path.join(IR_DIR, "ir_spectra.parquet")
OUTPUT_INDEX = os.path.join(IR_DIR, "unique_smiles_index.parquet")

FIGSHARE_ARTICLE_URL = "https://api.figshare.com/v2/articles/30734843"

def ensure_dirs():
    os.makedirs(IR_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def download_with_progress(url, dest_path, description="File"):
    if os.path.exists(dest_path):
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f"[IR Compiler] {description} existiert bereits ({size_mb:.1f} MB): {dest_path}")
        return True

    print(f"[IR Compiler] Starte Download von {description}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)

    start_time = time.time()
    try:
        with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_f:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            block_size = 1024 * 1024  # 1 MB

            while True:
                buf = resp.read(block_size)
                if not buf:
                    break
                downloaded += len(buf)
                out_f.write(buf)

                if total_size > 0:
                    percent = (downloaded / total_size) * 100.0
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    elapsed = time.time() - start_time
                    speed = mb_done / elapsed if elapsed > 0 else 0
                    print(f"\r  -> {percent:5.1f}% [{mb_done:.1f} MB / {mb_total:.1f} MB] @ {speed:.2f} MB/s", end="", flush=True)

        print(f"\n[IR Compiler] {description} erfolgreich heruntergeladen!")
        return True
    except Exception as e:
        print(f"\n[IR Compiler] Fehler beim Download von {description}: {e}")
        if os.path.exists(dest_path):
            try: os.remove(dest_path)
            except: pass
        return False

def fetch_squirl_download_links():
    try:
        req = urllib.request.Request(FIGSHARE_ARTICLE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        links = {}
        for f in data.get("files", []):
            links[f["name"]] = f["download_url"]
        return links
    except Exception as e:
        print(f"[IR Compiler] Fehler bei Figshare API: {e}")
        return {
            "SQuIRL_v1.0.h5": "https://ndownloader.figshare.com/files/59899805",
            "SQuIRL_v1.0_metadata.csv": "https://ndownloader.figshare.com/files/62764144"
        }

def compile_squirl_to_parquet(max_records=None):
    import h5py
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    if not os.path.exists(SQUIRL_H5_PATH) or not os.path.exists(SQUIRL_CSV_PATH):
        print("[IR Compiler] SQuIRL Dateien fehlen. Bitte zuerst herunterladen.")
        return False

    print("\n[IR Compiler] Lese SQuIRL Metadaten CSV...")
    df_meta = pd.read_csv(SQUIRL_CSV_PATH)
    total = len(df_meta)
    print(f"[IR Compiler] {total:,} Einträge in Metadaten gefunden.")

    if max_records and max_records < total:
        df_meta = df_meta.head(max_records)
        total = max_records

    print(f"[IR Compiler] Öffne HDF5 Datei: {SQUIRL_H5_PATH} ...")
    h5_file = h5py.File(SQUIRL_H5_PATH, "r")
    data_group = h5_file["data"]

    records = []
    print(f"[IR Compiler] Kompiliere IR-Spektren...")

    for i, row in df_meta.iterrows():
        mol_id = str(row["molecule_id"])
        if mol_id not in data_group:
            continue

        try:
            mol_grp = data_group[mol_id]
            ir_grp = mol_grp["infrared"]
            wn = ir_grp["wavenumbers"][...].tolist()
            intens = ir_grp["magnitudes"][...].tolist()

            smi = str(row.get("smiles", ""))
            formula = ""
            mw = 0.0
            inchikey = ""

            mol = Chem.MolFromSmiles(smi)
            if mol:
                formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
                mw = round(Descriptors.MolWt(mol), 2)
                inchikey = Chem.MolToInchiKey(mol)

            records.append({
                "id": f"SQUIRL_{mol_id}",
                "source": "SQuIRL",
                "source_type": "dft_calculated",
                "theory_level": "ωB97X-D/aug-cc-pVTZ",
                "name": f"QM9-{mol_id}",
                "smiles": smi,
                "inchikey": inchikey,
                "cas": "",
                "state": "gas",
                "formula": formula,
                "mw": mw,
                "wavenumbers": json.dumps([round(float(x), 2) for x in wn]),
                "intensities": json.dumps([round(float(x), 3) for x in intens]),
                "n_peaks": len(wn)
            })
        except Exception:
            continue

        if (i + 1) % 10000 == 0 or (i + 1) == total:
            print(f"\r  -> {i+1:,} / {total:,} verarbeitet ({len(records):,} gültig)...", end="", flush=True)

    h5_file.close()
    print(f"\n[IR Compiler] Erzeuge Parquet-Tabelle mit {len(records):,} Spektren...")

    df_out = pd.DataFrame(records)
    table = pa.Table.from_pandas(df_out)
    pq.write_table(table, OUTPUT_PARQUET, compression="zstd")
    print(f"[IR Compiler] Gespeichert unter: {OUTPUT_PARQUET}")

    # Create SMILES Index
    print("[IR Compiler] Erzeuge Substruktur-SMILES Index...")
    df_idx = df_out[["smiles", "inchikey", "id"]].drop_duplicates(subset=["smiles"])
    pq.write_table(pa.Table.from_pandas(df_idx), OUTPUT_INDEX, compression="zstd")
    print(f"[IR Compiler] Index gespeichert: {OUTPUT_INDEX}")
    return True

def run():
    ensure_dirs()
    print("=== HGTTD IR Spectra Downloader & Compiler ===")
    print("1. Figshare Links ermitteln...")
    links = fetch_squirl_download_links()

    h5_url = links.get("SQuIRL_v1.0.h5")
    csv_url = links.get("SQuIRL_v1.0_metadata.csv")

    if csv_url:
        download_with_progress(csv_url, SQUIRL_CSV_PATH, "SQuIRL Metadata CSV (59 MB)")
    if h5_url:
        print("\nSQuIRL HDF5 Datei hat ~2.1 GB.")
        confirm = input("Möchten Sie SQuIRL_v1.0.h5 jetzt herunterladen? (j/n): ").strip().lower()
        if confirm == "j":
            download_with_progress(h5_url, SQUIRL_H5_PATH, "SQuIRL HDF5 Dataset (2.1 GB)")
            compile_squirl_to_parquet()
        else:
            print("Download übersprungen.")

if __name__ == "__main__":
    run()
