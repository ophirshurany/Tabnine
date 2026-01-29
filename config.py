from typing import List
import os

try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings
    except ImportError:
        # Fallback to a simple class if pydantic is not installed or BaseSettings is missing
        # This ensures basic functionality even without pydantic-settings
        class BaseSettings:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
            class Config:
                env_file = ".env"

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    code_model_default: str = "google/gemini-2.0-flash-001"
    # Judge models as a comma-separated string in env, parsed to list here if needed, 
    # but BaseSettings handles List[str] if env is formatted right (json) or if we parse manual.
    # For simplicity with .env files, we'll take a string and parse it in a validator or post-init,
    # or just keep it simple and expect comma-separated string in env and handle parsing manually if pydantic fails.
    # To be safe and simple: use str and property or standard list parsing.
    judge_models_str: str = "google/gemini-2.0-flash-001" 
    
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1024
    llm_top_p: float = 1.0
    llm_frequency_penalty: float = 0.0
    llm_presence_penalty: float = 0.0

    @property
    def judge_models(self) -> List[str]:
        if not self.judge_models_str:
            return []
        return [m.strip() for m in self.judge_models_str.split(",") if m.strip()]

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        extra = "ignore" # Ignore extra env vars

# Try to load from .env using python-dotenv if available, as pydantic[dotenv] might not be there
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

settings = Settings()
