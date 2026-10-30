import os

from .paths import data_dir, sliced_files_dir
from .session import SessionStore

DATA_DIR = data_dir(__file__)
SESSIONS = SessionStore(DATA_DIR / "bambuddy" / "session.json")
SLICED_FILES_DIR = sliced_files_dir(uid=os.getuid() if hasattr(os, "getuid") else None)
