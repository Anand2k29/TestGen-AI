import os
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict
from ai_service import generate_tests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="TestGen AI")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_context: str
    model_choice: str  # "gemini" or "openrouter"
    model_name: str = "" # Selected OpenRouter model slug
    test_type: str     # "unit", "integration", or "edge"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/code", response_class=HTMLResponse)
async def code(request: Request):
    return templates.TemplateResponse("code.html", {"request": request})


@app.post("/api/generate")
async def generate(payload: GenerateRequest):
    if not payload.project_context.strip():
        raise HTTPException(status_code=400, detail="project_context cannot be empty.")

    if payload.model_choice not in ("gemini", "openrouter"):
        raise HTTPException(status_code=400, detail="model_choice must be 'gemini' or 'openrouter'.")

    if payload.test_type not in ("unit", "integration", "edge"):
        raise HTTPException(status_code=400, detail="test_type must be 'unit', 'integration', or 'edge'.")

    start = time.time()
    try:
        code = generate_tests(
            context=payload.project_context,
            model_choice=payload.model_choice,
            model_name=payload.model_name,
            test_type=payload.test_type,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        
    elapsed = round(time.time() - start, 2)

    # Count test functions as a rough proxy for "test cases"
    test_count = code.count("def test_")

    return {
        "code": code,
        "elapsed": elapsed,
        "test_count": test_count,
    }