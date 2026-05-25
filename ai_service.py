import os
import re
from typing import Any

import requests
from dotenv import load_dotenv


dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    load_dotenv()


GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

OPENROUTER_MODEL = "qwen/qwen3-coder:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SUPPORTED_OPENROUTER_MODELS = {
    "qwen/qwen3-coder:free",
    "baidu/cobuddy:free",
    "openrouter/owl-alpha",
    "deepseek/deepseek-v4-flash:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "poolside/laguna-xs.2:free",
    "poolside/laguna-m.1:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
}

TEST_TYPE_LABELS = {
    "unit": "unit tests",
    "integration": "integration tests",
    "edge": "edge case tests",
}

SYSTEM_PROMPT = (
    "You are an expert QA automation engineer specializing in Python and Pytest. "
    "Your sole job is to produce clean, runnable Pytest test code. "
    "Rules you MUST follow:\n"
    "1. Output ONLY raw Python source code - no markdown fences, no ```python, no backticks.\n"
    "2. No explanations, preamble, or commentary of any kind.\n"
    "3. Every test function must start with 'test_'.\n"
    "4. Include appropriate fixtures, mocks, and assertions.\n"
    "5. Add a brief inline comment above each test function describing what it covers."
)


def _build_user_prompt(context: str, test_type: str) -> str:
    label = TEST_TYPE_LABELS.get(test_type, "tests")
    return (
        f"Generate comprehensive Pytest {label} for the following specification.\n\n"
        f"--- SPECIFICATION START ---\n{context}\n--- SPECIFICATION END ---\n\n"
        "Remember: output only raw Python code, no markdown."
    )


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is not configured on the server.")
    return value


def mask_keys_in_message(msg: str) -> str:
    msg = re.sub(r"([?&]key=)[^&\s]*", r"\1AIzaSy***", msg)
    msg = re.sub(r"(Bearer\s+)sk-or-v1-[^&\s]*", r"\1sk-or-v1-***", msg)
    msg = re.sub(r"(sk-or-v1-)[^&\s]*", r"\1***", msg)
    return msg


def _post_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = requests.post(url, timeout=60, **kwargs)
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        message = f"{exc}. {body}".strip()
        raise RuntimeError(mask_keys_in_message(message)) from exc
    except requests.RequestException as exc:
        raise RuntimeError(mask_keys_in_message(str(exc))) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Model provider returned a non-JSON response.") from exc


def _call_gemini(context: str, test_type: str) -> str:
    prompt = _build_user_prompt(context, test_type)
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        },
    }

    data = _post_json(
        GEMINI_URL,
        params={"key": _get_required_env("GEMINI_API_KEY")},
        json=payload,
    )

    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response structure: {data}") from exc

    return _strip_markdown(raw)


def _call_openrouter(context: str, test_type: str, model_name: str = "") -> str:
    prompt = _build_user_prompt(context, test_type)
    requested_model = model_name.strip()
    target_model = (
        requested_model
        if requested_model in SUPPORTED_OPENROUTER_MODELS
        else OPENROUTER_MODEL
    )
    headers = {
        "Authorization": f"Bearer {_get_required_env('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://testgen-ai.local",
        "X-Title": "TestGen AI",
    }
    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    data = _post_json(OPENROUTER_URL, headers=headers, json=payload)

    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response structure: {data}") from exc

    return _strip_markdown(raw)


def _strip_markdown(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def generate_tests(context: str, model_choice: str, test_type: str, model_name: str = "") -> str:
    if model_choice == "gemini":
        return _call_gemini(context, test_type)
    if model_choice == "openrouter":
        return _call_openrouter(context, test_type, model_name)
    raise ValueError(f"Unknown model_choice: {model_choice!r}")
