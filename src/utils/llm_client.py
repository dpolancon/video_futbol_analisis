"""
src/utils/llm_client.py
-----------------------
Reusable Together AI client for the video_futbol_analisis project.

Reads credentials from the project .env file:
    OPEN_API_KEY   — your Together.ai API key  (tgp_v1_...)
    OPEN_API_BASE  — Together.ai base URL       (https://api.together.ai/v1)

Usage
-----
    from src.utils.llm_client import TogetherClient

    client = TogetherClient()
    result = client.chat(
        user_prompt="Describe a 4-4-2 defensive shape.",
        system_prompt="You are an expert football tactics analyst.",
    )
    print(result)

The client wraps the standard ``openai`` Python library pointed at Together.ai,
so any model available on https://api.together.ai/models can be used.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency guards
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    print(
        "  'python-dotenv' not installed.  Run:  pip install python-dotenv",
        file=sys.stderr,
    )
    raise

try:
    from openai import OpenAI
except ImportError:
    print(
        "  'openai' not installed.  Run:  pip install openai",
        file=sys.stderr,
    )
    raise

# ---------------------------------------------------------------------------
# Defaults (overridable via agent_config.yaml or constructor arguments)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 4_000
FALLBACK_BASE_URL = "https://api.together.ai/v1"

# ---------------------------------------------------------------------------
# Locate the project root so we can find .env regardless of cwd
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
# src/utils/llm_client.py  ->  go up 3 levels to reach the repo root
_PROJECT_ROOT = _THIS_FILE.parents[2]


def _load_env() -> None:
    """Load .env from the project root (non-destructive -- won't override existing vars)."""
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)  # fall back to standard search


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------
class TogetherClient:
    """
    Thin wrapper around the OpenAI SDK pointed at Together.ai.

    Parameters
    ----------
    api_key : str, optional
        Together.ai API key.  Falls back to ``OPEN_API_KEY`` env var.
    base_url : str, optional
        API base URL.  Falls back to ``OPEN_API_BASE`` env var, then the
        hardcoded Together.ai default.
    default_model : str, optional
        Model slug used when ``chat()`` is called without an explicit model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = DEFAULT_MODEL,
    ) -> None:
        _load_env()

        self.api_key = (
            api_key
            or os.getenv("OPEN_API_KEY")
            or os.getenv("TOGETHER_API_KEY")
        )
        if not self.api_key:
            raise EnvironmentError(
                "Together.ai API key not found.\n"
                "Set OPEN_API_KEY in your .env file or as an environment variable.\n"
                f"  Expected .env location: {_PROJECT_ROOT / '.env'}"
            )

        self.base_url = (
            base_url
            or os.getenv("OPEN_API_BASE")
            or os.getenv("TOGETHER_BASE_URL")
            or FALLBACK_BASE_URL
        )
        self.default_model = default_model

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ------------------------------------------------------------------
    # Core chat method
    # ------------------------------------------------------------------
    def chat(
        self,
        user_prompt: str,
        *,
        system_prompt: str = "You are a helpful assistant.",
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a chat request and return the text response.

        Parameters
        ----------
        user_prompt : str
            The user message.
        system_prompt : str
            Optional system-level instruction.
        model : str, optional
            Together.ai model slug.  Defaults to ``self.default_model``.
        temperature : float
            Sampling temperature (lower = more deterministic).
        max_tokens : int
            Maximum tokens in the completion.
        messages : list[dict], optional
            Full message history.  When provided, ``user_prompt`` and
            ``system_prompt`` are appended automatically.
        tools : list[dict], optional
            Tool/function definitions for structured outputs.
        **kwargs
            Any additional keyword arguments forwarded to
            ``client.chat.completions.create``.

        Returns
        -------
        str
            The model's text response.
        """
        resolved_model = model or self.default_model

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        else:
            # Append to the provided history
            if messages and messages[-1].get("role") != "user":
                messages.append({"role": "user", "content": user_prompt})

        create_kwargs: dict[str, Any] = dict(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if tools:
            create_kwargs["tools"] = tools

        response = self._client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Convenience: list available models
    # ------------------------------------------------------------------
    def list_models(self) -> list[dict]:
        """
        Return all models available on Together.ai for this account.

        Bypasses the openai SDK (which crashes on Together.ai's plain-array
        response) and calls the REST endpoint directly via httpx.

        Returns
        -------
        list[dict]
            Each dict has at minimum: 'id', 'display_name', 'type', 'running'.
        """
        import httpx

        resp = httpx.get(
            f"{self.base_url}/models",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        # Together.ai returns a plain list; guard against future wrapping
        if isinstance(data, list):
            return data
        return data.get("data", data)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"TogetherClient(base_url={self.base_url!r}, "
            f"default_model={self.default_model!r})"
        )
