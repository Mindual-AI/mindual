# scripts/query_rag.py
from __future__ import annotations

import sqlite3
from typing import List, Tuple

import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL_ID, DB_PATH
from src.index.build_embeddings_and_index import search


def answer_query(query: str, k: int = 5) -> None:
    """콘솔에서 RAG 파이프라인을 단독으로 테스트하는 함수."""

    print(f"\n[1] FAISS 검색 시작: query = {query!r}, k = {k}")
    results: List[Tuple[int, float]] = search("chunks", query, k=k)
    print(f"[1] FAISS 검색 결과: {len(results)}개\n{results}\n")

    # 2. context 로드 (DB에서 content 조회)
    conn = sqlite3.connect(DB_PATH)
    contexts: list[str] = []
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
            contexts.append(f"[p.{page}] {content}")
            if page_img:
                print(f"🖼️ page image: {page_img}")
    finally:
        conn.close()

    if not contexts:
        print("[2] 관련 문서 컨텍스트가 없습니다.")
    else:
        print(f"[2] 컨텍스트 문단 개수: {len(contexts)}")

    # 3. Gemini로 RAG 답변 생성
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY가 설정되어 있지 않습니다.")
        return

    print("[3] Gemini 설정 및 요청 시작")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL_ID)

    prompt = (
        "다음 매뉴얼 내용에 근거하여 질문에 답하세요.\n\n"
        f"질문: {query}\n\n"
        "관련 문서:\n" + "\n\n".join(contexts)
    )

    try:
        resp = model.generate_content(prompt)
    except Exception as e:
        print("❌ Gemini 호출 중 예외 발생:")
        print(repr(e))
        return

    text = getattr(resp, "text", None)
    if not text and hasattr(resp, "candidates"):
        try:
            text = resp.candidates[0].content.parts[0].text
        except Exception:
            text = None

    print("\n💬 Gemini 답변:\n", text or "⚠️ Gemini 응답이 없습니다.")


if __name__ == "__main__":
    # 테스트용 기본 질문
    answer_query("필터 청소 어떻게 하나요?", k=3)
