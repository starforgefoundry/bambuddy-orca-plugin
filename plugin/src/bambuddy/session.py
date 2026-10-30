import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

SESSION_FILE_MODE = 0o600


@dataclass(frozen=True)
class Session:
    instance_url: str
    api_key: str | None
    username: str | None


class SessionStore:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> Session | None:
        try:
            return Session(**json.loads(self._path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def save(self, session: Session) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(asdict(session)), encoding="utf-8")
        os.chmod(self._path, SESSION_FILE_MODE)

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)
