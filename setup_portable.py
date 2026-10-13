import os
import sys
import urllib.request
import zipfile
import subprocess
import shutil

PYTHON_VERSION = "3.10.11"
ZIP_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PORTABLE_DIR = os.path.abspath("python-portable")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

def setup_portable():
    print("=== Portable Python Setup ===")
    
    if os.path.exists(PORTABLE_DIR):
        print(f"Das Verzeichnis '{PORTABLE_DIR}' existiert bereits.")
        confirm = input("Möchten Sie es überschreiben? (j/n): ").strip().lower()
        if confirm != 'j':
            print("Setup abgebrochen.")
            return
        shutil.rmtree(PORTABLE_DIR)
        
    os.makedirs(PORTABLE_DIR, exist_ok=True)
    
    # 1. Download Python embeddable
    zip_path = os.path.join(PORTABLE_DIR, "python_embed.zip")
    print(f"Lade portable Version Python {PYTHON_VERSION} herunter...")
    try:
        urllib.request.urlretrieve(ZIP_URL, zip_path)
        print("Download abgeschlossen.")
    except Exception as e:
        print(f"Fehler beim Download: {e}")
        return

    # 2. Extract ZIP
    print("Entpacke Python...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(PORTABLE_DIR)
        print("Entpacken abgeschlossen.")
    except Exception as e:
        print(f"Fehler beim Entpacken: {e}")
        return
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    # 3. Enable site-packages in ._pth file
    pth_file = os.path.join(PORTABLE_DIR, f"python310._pth")
    if os.path.exists(pth_file):
        print("Passe ._pth Datei an, um site-packages zu erlauben...")
        with open(pth_file, "r") as f:
            content = f.read()
        
        # Uncomment 'import site'
        if "#import site" in content:
            content = content.replace("#import site", "import site")
        elif "import site" not in content:
            content += "\nimport site\n"
            
        with open(pth_file, "w") as f:
            f.write(content)

    # 4. Download get-pip.py
    pip_script = os.path.join(PORTABLE_DIR, "get-pip.py")
    print("Lade pip Installer herunter...")
    try:
        urllib.request.urlretrieve(GET_PIP_URL, pip_script)
    except Exception as e:
        print(f"Fehler beim Download von get-pip.py: {e}")
        return

    # 5. Run get-pip.py using portable python
    python_exe = os.path.join(PORTABLE_DIR, "python.exe")
    print("Installiere pip...")
    try:
        subprocess.run([python_exe, pip_script], check=True)
        print("pip erfolgreich installiert.")
    except Exception as e:
        print(f"Fehler bei der pip Installation: {e}")
        return
    finally:
        if os.path.exists(pip_script):
            os.remove(pip_script)

    # 6. Install dependencies
    dependencies = ["PySide6", "rdkit", "pandas"]
    print(f"Installiere Bibliotheken: {', '.join(dependencies)}...")
    try:
        # Run pip install
        subprocess.run([python_exe, "-m", "pip", "install"] + dependencies, check=True)
        print("Alle Bibliotheken erfolgreich installiert.")
    except Exception as e:
        print(f"Fehler bei der Installation der Abhängigkeiten: {e}")
        return

    print("\n=== Portable Python erfolgreich eingerichtet! ===")
    print(f"Verzeichnis: {PORTABLE_DIR}")

if __name__ == "__main__":
    setup_portable()
