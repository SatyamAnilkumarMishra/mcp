"""
The "target" abstraction: whatever model you're evaluating.

WHY THIS EXISTS: the harness should not care whether it's talking to
Gemini, OpenAI, a local vLLM server, or your own RAG pipeline's final
answer-generation step. Everything downstream (runner, evaluators,
reporting) only depends on this one interface: give it a prompt, get
back a TargetResponse. Build this abstraction second (right after
evaluators/base.py) — it's the other half of the "everything plugs into
a common shape" design.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel


class TargetResponse(BaseModel):
    """
    Standardized response, regardless of provider.

    latency_ms and usage are captured here — not bolted on later —
    because "how much did this cost / how slow was it" are first-class
    eval metrics, not an afterthought. A model that's 2% more accurate
    but 5x slower and 10x more expensive is a genuinely different
    trade-off decision, and you can't make that call if latency/usage
    aren't tracked from day one.

    raw: the full provider response, kept for debugging when something
    looks wrong and you need to see exactly what the API actually sent
    back (finish_reason, safety blocks, etc.) beyond just the text.
    """

    text: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    raw: Optional[Dict[str, Any]] = None


class BaseTarget(ABC):
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.config = kwargs

    @abstractmethod
    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None, **generation_kwargs
    ) -> TargetResponse:
        """
        Async by design: even the very first target you build should be
        async, because the runner will eventually fire many of these
        concurrently under a semaphore. Building this sync first and
        retrofitting async later is a common self-inflicted headache —
        skip it by starting async.
        """
        pass
