# src/api/routes.py
from __future__ import annotations

from typing import List, Optional

import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import google.generativeai as genai

from src.config import DB_PATH, GEMINI_API_KEY, GEMINI_MODEL_ID
from src.index.build_embeddings_and_index import search
from src.agent.agent_init import answer_query  # 나중에 /answer, /propose 등에 사용 가능

router = APIRouter()

# ---------- Pydantic 모델 ----------

class RagRequest(BaseModel):
    query: str
    k: int = 5


class RagContext(BaseModel):
    text: str
    page: Optional[int] = None
    manual_id: Optional[int] = None
    page_image: Optional[str] = None
    score: float


class RagResponse(BaseModel):
    answer: str
    contexts: List[RagContext]


# ---------- Gemini 세팅 (한 번만) ----------

genai.configure(api_key=GEMINI_API_KEY)
_gemini_model = genai.GenerativeModel(GEMINI_MODEL_ID)


def _call_gemini(prompt: str) -> str:
    """Gemini 호출 헬퍼: resp.text 없을 때 candidates 에서 꺼내오기."""
    resp = _gemini_model.generate_content(prompt)
    text = getattr(resp, "text", None)

    if not text and hasattr(resp, "candidates") and resp.candidates:
        parts = resp.candidates[0].content.parts
        if parts and getattr(parts[0], "text", None):
            text = parts[0].text

    return text or "응답 생성에 실패했습니다."


# ---------- /rag/query 엔드포인트 ----------

@router.post("/rag/query", response_model=RagResponse)
def rag_query(body: RagRequest) -> RagResponse:
    # 1) FAISS 검색
    try:
        results = search("chunks", body.query, k=body.k)
    except Exception as e:
        # search 에서 에러 날 경우를 대비한 간단한 방어 코드
        raise HTTPException(status_code=500, detail=f"벡터 검색 중 오류가 발생했습니다: {e}")

    # 2) DB에서 컨텍스트 로드
    conn = sqlite3.connect(DB_PATH)
    contexts: List[RagContext] = []

    try:
        for rid, score in results:
            row = conn.execute(
                """
                SELECT c.content, c.manual_id, c.page, p.path
                FROM chunks c
                LEFT JOIN page_images p
                  ON c.manual_id = p.manual_id AND c.page = p.page
                WHERE c.id = ?
                """,
                (rid,),
            ).fetchone()

            if not row:
                continue

            content, manual_id, page, page_img = row
            contexts.append(
                RagContext(
                    text=content,
                    page=page,
                    manual_id=manual_id,
                    page_image=page_img,
                    score=score,
                )
            )
    finally:
        conn.close()

    # 3) 프롬프트 구성
    if contexts:
        context_strs = []
        for c in contexts:
            prefix = f"[p.{c.page}] " if c.page is not None else ""
            context_strs.append(prefix + c.text)

        joined_context = "\n\n".join(context_strs)
    else:
        joined_context = "(관련 문서를 찾지 못했습니다.)"

    prompt = (
        "너는 가전제품 사용설명서를 대신 읽어주는 한국어 도우미야.\n"
        "아래에 제공된 매뉴얼 내용만 근거로, 사용자가 이해하기 쉽고 안전하게 답변해 줘.\n"
        "- 매뉴얼에 없는 내용은 추측하지 말고 '매뉴얼에 없는 내용입니다'라고 말할 것.\n"
        "- 단계가 필요한 경우 1,2,3 순서로 정리할 것.\n\n"
        f"질문: {body.query}\n\n"
        f"관련 매뉴얼 발췌:\n{joined_context}\n"
    )

    # 4) Gemini로 최종 답변 생성
    answer = _call_gemini(prompt)

    return RagResponse(answer=answer, contexts=contexts)
