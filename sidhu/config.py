from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os


def data_dir() -> Path:
    override = os.environ.get("SIDHU_DATA_DIR")
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    root = Path(override) if override else Path(base) / "SidhuAI"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Settings:
    model_path: str = ""
    microphone: int | None = None
    memory_enabled: bool = False
    productivity_enabled: bool = False
    history_enabled: bool = False
    followup_seconds: int = 12
    speech_enabled: bool = True
    speech_rate: int = 165
    voice_id: str = ""
    autostart: bool = False
    approved_folders: list[str] = field(default_factory=lambda: [str(Path.home() / "Downloads")])
    window_control_enabled: bool = False
    screen_capture_enabled: bool = False
    allowed_apps: list[str] = field(default_factory=lambda: ["chrome", "edge", "explorer", "notepad"])
    ai_base_url: str = "http://localhost:11434/v1"
    ai_model: str = ""
    ai_context_enabled: bool = False
    ai_key_env: str = "SIDHU_API_KEY"
    lightweight: bool = False
    avatar_enabled: bool = False
    browser_enabled: bool = False
    browser_domains: list[str] = field(default_factory=list)
    browser_executable: str = ""
    workflows: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return cls()
        values = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temp.replace(path)
