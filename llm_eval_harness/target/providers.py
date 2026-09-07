"""
Concrete provider adapters: Gemini and any OpenAI-compatible endpoint.

WHY BOTH: an OpenAI-*compatible* target (not just literal OpenAI) means
this one class also works with local servers (vLLM, Ollama's OpenAI
shim, LM Studio, etc.) and other hosted providers that mimic the OpenAI
API shape — you just swap `base_url`. That's a much bigger unlock than
it looks: you get "works with almost anything" for close to free.

RETRY LOGIC (added — this was a gap in the original version): the first
draft of this harness fired one API call per sample with no retry. In
an eval run of, say, 200 samples, a single transient 429/5xx would kill
that entire sample's `asyncio.gather()` task. `_call_with_retry` below
wraps both providers with exponential backoff on failure. This is a
good general lesson for anything hitting a network API in a loop: retry
logic isn't optional polish, it's what separates "runs once on 3 rows"
from "actually usable on a real benchmark."

RATE-LIMIT AWARE (updated): a 429 quota error tells you exactly how
long to wait (e.g. "Please retry in 12.3s"). Generic exponential
backoff is often too short for that wait, so `_call_with_retry` now
parses the server's own suggested delay when the error message
contains one, and falls back to exponential backoff otherwise.
"""

import asyncio
import re
import time
from typing import Optional, Dict, Any, Callable, Awaitable, TypeVar
from target.base import BaseTarget, TargetResponse

# Gemini
from google import genai
from google.genai import types

# OpenAI
import openai

T = TypeVar("T")


async def _call_with_retry(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> T:
    """Exponential backoff retry for a single async API call, with a
    rate-limit-aware override: if the exception message contains a
    server-suggested "retry in Ns" delay (as Gemini's 429 quota errors
    do), wait that long (plus a small buffer) instead of guessing with
    2**attempt.

    Kept as a free function (not a method) so both provider classes can
    share it without inheritance gymnastics — a small illustration that
    not everything needs to live on a base class.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            match = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e))
            if match:
                delay = float(match.group(1)) + 1  # small buffer
            else:
                delay = base_delay * (2 ** attempt)
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    raise last_exc  # re-raise the last failure after exhausting retries


class GeminiTarget(BaseTarget):
    def __init__(self, model_name: str, api_key: str, **kwargs):
        super().__init__(model_name, **kwargs)
        self.client = genai.Client(api_key=api_key)

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None, **generation_kwargs
    ) -> TargetResponse:
        start = time.perf_counter()

        config_dict = {**self.config, **generation_kwargs}
        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        config = types.GenerateContentConfig(**config_dict)

        response = await _call_with_retry(
            lambda: self.client.aio.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
        )
