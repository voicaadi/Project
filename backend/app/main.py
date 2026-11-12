from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.security.rate_limit import limiter
from app.api.device_routes import router as device_router
from app.api.terminal_ws import router as terminal_ws_router
from app.api.auth_routes import router as auth_router
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from typing import Literal
from app.api.workspace_routes import router as workspace_router
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.ai_service import ask_gemini
from app.services.docker_service import (
    get_containers,
    get_docker_info,
    run_docker_operation,
)


app = FastAPI(
    title="DevOps AI Assistant",
    description="AI-powered DevOps automation platform",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(terminal_ws_router)
app.include_router(device_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
async def root():
    return {
        "application": "DevOps AI Assistant",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "backend",
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        answer = ask_gemini(request.message)
        return {"response": answer}
    except Exception as e:
        print("GEMINI ERROR:", repr(e))
        raise HTTPException(status_code=500, detail="AI request failed. Check backend logs.")


@app.get("/api/docker/containers")
def docker_containers():
    try:
        return {"containers": get_containers()}
    except Exception as e:
        print("DOCKER ERROR:", repr(e))
        raise HTTPException(
            status_code=503,
            detail="Docker connection failed. Check backend logs.",
        )


@app.get("/api/docker/info")
def docker_info():
    try:
        return get_docker_info()
    except Exception as e:
        print("DOCKER ERROR:", repr(e))
        raise HTTPException(
            status_code=503,
            detail="Docker connection failed. Check backend logs.",
        )


class DockerOperationRequest(BaseModel):
    action: Literal["ps", "images", "logs", "inspect"]
    target: str | None = Field(default=None, max_length=128)


@app.post("/api/docker/terminal")
def docker_terminal(request: DockerOperationRequest):
    try:
        output = run_docker_operation(
            action=request.action,
            target=request.target,
        )
        return {"success": True, "output": output}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print("DOCKER TERMINAL ERROR:", repr(e))
        raise HTTPException(
            status_code=503,
            detail="Docker operation failed. Check backend logs.",
        )
