import os
import sys
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict

# Ensure project root is in sys.path so we can import ai_service cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_service import generate_tests

app = FastAPI(title="TestGen AI")

# Robust template directory resolution for Vercel serverless environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSSIBLE_DIRS = [
    os.path.join(BASE_DIR, "templates"),
    os.path.join(BASE_DIR, "api", "templates"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"),
    "templates"
]
template_dir = next((d for d in POSSIBLE_DIRS if os.path.isdir(d)), os.path.join(BASE_DIR, "templates"))
templates = Jinja2Templates(directory=template_dir)


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
