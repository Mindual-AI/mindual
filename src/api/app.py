# src/api/app.py
# FastAPI 진입점
from fastapi import FastAPI
from src.api.routes import router as api_router

app = FastAPI(title="Manual Agent (MVP)")
app.include_router(api_router, prefix="/api")

# 헬스체크
@app.get("/health")
def health():
    return {"ok": True}
