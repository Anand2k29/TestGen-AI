import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from ai_service import generate_tests


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "api" / "templates"

app = FastAPI(title="TestGen AI")


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_context: str
    model_choice: Literal["gemini", "openrouter"]
    model_name: str = ""
    test_type: Literal["unit", "integration", "edge"]


def render_template(name: str) -> HTMLResponse:
    template_path = TEMPLATE_DIR / name
    if not template_path.is_file():
        raise HTTPException(status_code=500, detail=f"Missing template: {name}")

    return HTMLResponse(template_path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
async def index():
    return render_template("index.html")


@app.get("/code", response_class=HTMLResponse)
async def code():
    return render_template("code.html")


@app.post("/api/generate")
async def generate(payload: GenerateRequest):
    project_context = payload.project_context.strip()
    if not project_context:
        raise HTTPException(status_code=400, detail="project_context cannot be empty.")

    started_at = time.perf_counter()
    try:
        code = generate_tests(
            context=project_context,
            model_choice=payload.model_choice,
            model_name=payload.model_name,
            test_type=payload.test_type,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    elapsed = round(time.perf_counter() - started_at, 2)
    return {
        "code": code,
        "elapsed": elapsed,
        "test_count": code.count("def test_"),
    }
