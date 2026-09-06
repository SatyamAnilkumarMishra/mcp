# Central config, sourced from environment variables (see .env.example).
#
# WHY THIS EXISTS AS ITS OWN FILE: keeping "where do secrets/config come
# from" in exactly one place means every other file just imports
# `settings` and never touches os.getenv() directly. That matters once
# you have several modules that need an API key — you don't want six
# different files each deciding independently how to fall back if an
# env var is missing.

import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = Field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    max_concurrent: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT", "1"))
    )
    gemini_judge_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_JUDGE_MODEL", "gemini-3.6-flash")
    )
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_base_url: str = Field(
        default_factory=lambda: os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    )


settings = Settings()
