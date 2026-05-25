import os
import requests
import re
from dotenv import load_dotenv

# Robustly load the local .env relative to the script, overriding any empty process vars
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Update default model to gemini-2.5-flash (active in 2026) to fix the 404 error
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

OPENROUTER_MODEL = "meta-llama/llama-3-8b-instruct:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TEST_TYPE_LABELS = {
    "unit": "unit tests",
    "integration": "integration tests",
    "edge": "edge case tests",
}

SYSTEM_PROMPT = (
    "You are an expert QA automation engineer specializing in Python and Pytest. "
    "Your sole job is to produce clean, runnable Pytest test code. "
    "Rules you MUST follow:\n"
    "1. Output ONLY raw Python source code — no markdown fences, no ```python, no backticks.\n"
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


def mask_keys_in_message(msg: str) -> str:
    """Mask credentials in traceback messages to keep keys safe."""
    msg = re.sub(r'([?&]key=)[^&\s]*', r'\1AIzaSy***', msg)
    msg = re.sub(r'(Bearer\s+)sk-or-v1-[^&\s]*', r'\1sk-or-v1-***', msg)
    msg = re.sub(r'(sk-or-v1-)[^&\s]*', r'\1***', msg)
    return msg


def _call_gemini(context: str, test_type: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in your .env file.")

    prompt = _build_user_prompt(context, test_type)

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        },
    }

    try:
        response = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(mask_keys_in_message(str(exc))) from exc
        
    data = response.json()

    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response structure: {data}") from exc

    return _strip_markdown(raw)


def _call_openrouter(context: str, test_type: str, model_name: str = "") -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in your .env file.")

    prompt = _build_user_prompt(context, test_type)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://testgen-ai.local",   # required by OpenRouter
        "X-Title": "TestGen AI",
    }

    target_model = model_name if model_name else OPENROUTER_MODEL

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(mask_keys_in_message(str(exc))) from exc
        
    data = response.json()

    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenRouter response structure: {data}") from exc

    return _strip_markdown(raw)


def _strip_markdown(text: str) -> str:
    """Remove any markdown code fences the model may have slipped in."""
    lines = text.strip().splitlines()
    # Drop leading ```python / ``` fences
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def generate_tests(context: str, model_choice: str, test_type: str, model_name: str = "") -> str:
    """Public entry point called by the FastAPI route."""
    if model_choice == "gemini":
        return _call_gemini(context, test_type)
    elif model_choice == "openrouter":
        return _call_openrouter(context, test_type, model_name)
    else:
        raise ValueError(f"Unknown model_choice: {model_choice!r}")