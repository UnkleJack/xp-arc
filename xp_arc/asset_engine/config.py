"""Configuration loader for Asset Engine."""
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerConfig(BaseModel):
    cron: str = "0 6,18 * * *"
    manual_trigger: bool = True
    max_prompts_per_run: int = 20


class BrowserConfig(BaseModel):
    enabled: bool = True
    platforms: list[str] = ["chatgpt", "openrouter", "copilot", "grok"]
    headless: bool = True
    timeout_seconds: int = 120
    profile_dir: str = "~/.asset-engine/browser-profiles"


class APIConfig(BaseModel):
    enabled: bool = True
    providers: list[str] = ["openrouter", "fal", "replicate", "comfyui"]
    budget_per_run_usd: float = 5.00
    comfyui_endpoint: str = "http://zo.computer:8188"


class GenerationConfig(BaseModel):
    browser: BrowserConfig = BrowserConfig()
    api: APIConfig = APIConfig()


class StyleEnginesConfig(BaseModel):
    active: list[str] = ["simpsons-horror", "disney-dark"]
    max_per_run: int = 10


class ReviewConfig(BaseModel):
    interface: str = "obsidian"
    vault_path: str = "~/asset-engine/review-vault"
    auto_open_on_run: bool = False


class GDriveConfig(BaseModel):
    enabled: bool = True
    remote_name: str = "asset-engine"
    folder_id: str = ""
    sync_on_review: bool = True


class SyncConfig(BaseModel):
    gdrive: GDriveConfig = GDriveConfig()


class UnityConfig(BaseModel):
    enabled: bool = False
    output_dir: str = "~/asset-engine/unity-assets"


class DatabaseConfig(BaseModel):
    path: str = "~/asset-engine/metadata.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "~/asset-engine/logs/engine.log"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")
    
    scheduler: SchedulerConfig = SchedulerConfig()
    style_engines: StyleEnginesConfig = StyleEnginesConfig()
    generation: GenerationConfig = GenerationConfig()
    review: ReviewConfig = ReviewConfig()
    sync: SyncConfig = SyncConfig()
    unity: UnityConfig = UnityConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        path = Path(path).expanduser()
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()


# Global config instance
config = Config.load()