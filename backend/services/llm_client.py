import json
import os
import re
from typing import Any, Optional

try:
    from dotenv import load_dotenv

    _ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
except Exception:
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Google Gemini — free tier via Google AI Studio (https://aistudio.google.com/apikey).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)


def gemini_available() -> bool:
    key = GEMINI_API_KEY.strip()
    return bool(key and not key.lower().startswith("your"))


def openai_available() -> bool:
    key = OPENAI_API_KEY.strip()
    return bool(key and not key.startswith("sk-your"))


def llm_available() -> bool:
    return gemini_available() or openai_available()


def active_model() -> str:
    if gemini_available():
        return GEMINI_MODEL
    if openai_available():
        return OPENAI_MODEL
    return "offline"


async def _gemini_chat(system: str, user: str, temperature: float, max_tokens: int) -> str:
    import httpx

    url = f"{GEMINI_BASE_URL.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    # 2.5 models "think" by default and can spend the whole token budget on
    # reasoning; disable it for these short, grounded narrations.
    if GEMINI_MODEL.startswith("gemini-2.5"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation_config,
            },
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()


async def _openai_chat(system: str, user: str, temperature: float, max_tokens: int) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


async def chat_completion(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> tuple[str, str]:
    """Returns (content, source) where source is 'gemini', 'openai', or 'heuristic'."""
    if gemini_available():
        try:
            return await _gemini_chat(system, user, temperature, max_tokens), "gemini"
        except Exception:
            pass

    if openai_available():
        try:
            return await _openai_chat(system, user, temperature, max_tokens), "openai"
        except Exception:
            pass

    return _heuristic_fallback(system, user), "heuristic"


def _heuristic_fallback(system: str, user: str) -> str:
    if "JSON" in system or "json" in system.lower():
        return "{}"
    if "experiment brief" in system.lower() or "Experiment Brief" in user:
        return _template_brief_from_context(user)
    return (
        "AI copilot is running in offline mode (set OPENAI_API_KEY in backend/.env for full LLM answers). "
        "Use the structured sample data and recommendations below to guide your next experiments."
    )


def _template_brief_from_context(user: str) -> str:
    return (
        "# Experiment Brief (offline template)\n\n"
        "Set `OPENAI_API_KEY` in backend/.env to generate a full narrative brief.\n\n"
        "## Context summary\n\n"
        f"{user[:4000]}\n\n"
        "## Suggested next steps\n\n"
        "1. Run ranked dopant recommendations from the AI panel.\n"
        "2. Characterize with XRD and VSM; link uploads to the sample record.\n"
        "3. Label outcomes (success / partial / fail) to improve future rankings.\n"
    )


def parse_json_from_llm(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None
