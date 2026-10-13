import os
import json

CONFIG_FILE_NAME = "config.json"

DEFAULT_CONFIG = {
    "language": "de",
    "source_db_path": r"C:\Users\wotan\OneDrive\Dokumente\PythonProjekte\SDF-Verwaltung\nmrshiftdb2_3D_OPTIMIZED_with_props.sdf",
    "local_sdf_name": "nmrshiftdb2_3D_OPTIMIZED_with_props.sdf",
    "nmrexp_parquet_path": os.path.join("nmr_exp", "NMRexp_10to24_1_1004.parquet"),
    "search_nucleus": "all",
    "search_mode": "exact",
    "max_hits": 100
}

def get_config_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, CONFIG_FILE_NAME)

def load_config():
    """
    Loads configuration from config.json.
    Creates default config.json if not present.
    """
    path = get_config_path()
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Merge with defaults in case keys are missing
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except Exception as e:
        print(f"[config_manager] Fehler beim Laden von {CONFIG_FILE_NAME}: {e}. Verwende Standardwerte.")
        return dict(DEFAULT_CONFIG)

def save_config(config_dict):
    """
    Saves configuration dict to config.json.
    """
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[config_manager] Fehler beim Speichern von {CONFIG_FILE_NAME}: {e}")
        return False

def get_config_value(key, default=None):
    cfg = load_config()
    return cfg.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

def set_config_value(key, value):
    cfg = load_config()
    cfg[key] = value
    return save_config(cfg)

def get_language():
    lang = get_config_value("language", "de")
    return lang if lang in ("de", "en") else "de"

def set_language(lang):
    if lang in ("de", "en"):
        return set_config_value("language", lang)
    return False

def get_source_db_path():
    return get_config_value("source_db_path", DEFAULT_CONFIG["source_db_path"])

def set_source_db_path(path):
    return set_config_value("source_db_path", path)

def get_local_sdf_name():
    return get_config_value("local_sdf_name", DEFAULT_CONFIG["local_sdf_name"])

def get_nmrexp_rel_path():
    return get_config_value("nmrexp_parquet_path", DEFAULT_CONFIG["nmrexp_parquet_path"])

def get_search_nucleus():
    return get_config_value("search_nucleus", DEFAULT_CONFIG["search_nucleus"])

def set_search_nucleus(nuc):
    return set_config_value("search_nucleus", nuc)

def get_search_mode():
    return get_config_value("search_mode", DEFAULT_CONFIG["search_mode"])

def set_search_mode(mode):
    return set_config_value("search_mode", mode)

def get_max_hits():
    return int(get_config_value("max_hits", DEFAULT_CONFIG["max_hits"]))

def set_max_hits(limit):
    return set_config_value("max_hits", int(limit))
