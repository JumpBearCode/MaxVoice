from pathlib import Path


def app_data_dir() -> Path:
    p = Path.home() / "Library" / "Application Support" / "maxvoice"
    p.mkdir(parents=True, exist_ok=True)
    return p


def audio_dir() -> Path:
    p = app_data_dir() / "audio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return app_data_dir() / "maxvoice.db"


def config_path() -> Path:
    return app_data_dir() / "config.json"
