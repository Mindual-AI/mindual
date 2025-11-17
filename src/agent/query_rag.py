# scripts/query_rag.py
from src.index.build_embeddings_and_index import search
from src.config import GEMINI_API_KEY, GEMINI_MODEL_ID, DB_PATH
import google.generativeai as genai
import sqlite3

def answer_query(query: str, k: int = 5):
    # 1. FAISS 검색
    results = search("chunks", query, k=k)

    # 2. context 로드 (DB에서 content 조회)
    conn = sqlite3.connect(DB_PATH)
    contexts = []
    for rid, score in results:
        c = conn.execute("""
            SELECT c.content, c.manual_id, c.page, p.path
            FROM chunks c
            LEFT JOIN page_images p
              ON c.manual_id = p.manual_id AND c.page = p.page
            WHERE c.id=?
        """, (rid,)).fetchone()
        if c:
            content, manual_id, page, page_img = c
            contexts.append(f"[p.{page}] {content}")
            if page_img:
                print(f"🖼️ page image: {page_img}")
    conn.close()

    # 3. Gemini로 RAG 답변 생성
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL_ID)

    prompt = f"다음 매뉴얼 내용에 근거하여 질문에 답하세요.\n\n질문: {query}\n\n관련 문서:\n" + "\n\n".join(contexts)
    resp = model.generate_content(prompt)

    text = getattr(resp, "text", None)
    if not text and hasattr(resp, "candidates"):
        text = resp.candidates[0].content.parts[0].text
    print("\n💬 Gemini 답변:\n", text or "⚠️ Gemini 응답이 없습니다.")

if __name__ == "__main__":
    answer_query("필터 청소 어떻게 하나요?", k=3)
