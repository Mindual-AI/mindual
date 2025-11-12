# src/api/routes.py
# /search /answer /propose 등
from fastapi import APIRouter, HTTPException
from src.agent.agent_init import answer_query

router = APIRouter()

@router.post("/answer")
def post_answer(payload: dict):
    try:
        out = answer_query(payload or {})
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
