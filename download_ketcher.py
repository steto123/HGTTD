import os
import sys
import urllib.request
import json
import zipfile
import shutil

def download_ketcher(dest_dir="ketcher"):
    print("Suche nach der neuesten Ketcher-Version...")
    api_url = "https://api.github.com/repos/epam/ketcher/releases/latest"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(api_url, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                name = asset.get("name", "")
                if "ketcher-standalone" in name and name.endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    print(f"Gefunden: {name} ({download_url})")
                    break
            
            if not download_url:
                # Fallback to a hardcoded working version if not found in assets
                download_url = "https://github.com/epam/ketcher/releases/download/v2.26.0/ketcher-standalone-2.26.0.zip"
                print(f"Verwende Fallback-URL: {download_url}")
    except Exception as e:
        print(f"Fehler beim Abrufen der API ({e}). Verwende Standard-Fallback...")
        download_url = "https://github.com/epam/ketcher/releases/download/v2.26.0/ketcher-standalone-2.26.0.zip"

    zip_path = "ketcher_standalone.zip"
    print(f"Lade Ketcher herunter von {download_url}...")
    try:
        urllib.request.urlretrieve(download_url, zip_path)
        print("Download abgeschlossen.")
    except Exception as e:
        print(f"Download fehlgeschlagen: {e}")
        return False

    print(f"Entpacke nach '{dest_dir}'...")
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        print("Entpacken erfolgreich.")
    except Exception as e:
        print(f"Fehler beim Entpacken: {e}")
        return False
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    # In standard zip, there might be a nested folder, or the files are directly in 'ketcher'
    # Let's check if there is only one subdirectory inside and move files up if so.
    subdirs = [os.path.join(dest_dir, d) for d in os.listdir(dest_dir) if os.path.isdir(os.path.join(dest_dir, d))]
    if len(subdirs) == 1 and not os.path.exists(os.path.join(dest_dir, "index.html")):
        single_dir = subdirs[0]
        print(f"Verschiebe Dateien aus Unterverzeichnis {single_dir} nach oben...")
        for item in os.listdir(single_dir):
            shutil.move(os.path.join(single_dir, item), os.path.join(dest_dir, item))
        os.rmdir(single_dir)

    print("Ketcher Setup abgeschlossen.")
    return True

if __name__ == "__main__":
    download_ketcher()
