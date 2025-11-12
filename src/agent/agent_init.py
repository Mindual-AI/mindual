# src/agent/agent_init.py
# OpenAI Agent SDK 초기화
import google.generativeai as genai
from typing import Dict, Any, List
from src.config import GEMINI_API_KEY, GEMINI_MODEL_ID
from src.agent.system_prompt import SYSTEM_PROMPT
from src.agent.mcp_tools import search_manual, lookup_trouble, propose_next_action

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL_ID) if GEMINI_API_KEY else None

def _build_context(query: str, hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return "검색 결과 없음."
    lines = []
    for i, h in enumerate(hits, 1):
        prefix = f"[{i}] (page {h.get('page','?')})"
        lines.append(f"{prefix}\n{h['content']}\n")
    return "\n".join(lines)

def answer_query(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload = {
      "query": "...",
      "device_state": {...},    # optional
      "error_code": "E05"       # optional
    }
    """
    query = (payload.get("query") or "").strip()
    device_state = payload.get("device_state") or {}
    error_code = payload.get("error_code")

    # 1) 능동 제안 (아주 간단한 규칙)
    proactive = propose_next_action(device_state) if device_state else None

    # 2) 오류코드가 오면 우선 조회
    trouble_txt = None
    if error_code:
        t = lookup_trouble(error_code)
        if t:
            trouble_txt = f"[{error_code}] 증상: {t['symptom']}\n원인: {t['cause']}"

    # 3) 매뉴얼 검색
    hits = search_manual(query if query else (error_code or "기본 사용"))
    context_txt = _build_context(query, hits)

    if not _model:
        # LLM이 없으면 검색 결과만 반환
        return {
            "answer": context_txt,
            "proactive": proactive,
            "trouble": trouble_txt,
            "used_llm": False
        }

    # 4) LLM 요약/응답
    prompt = f"""{SYSTEM_PROMPT}

사용자 질문:
{query or error_code or '질문 없음'}

검색 컨텍스트(매뉴얼 발췌):
{context_txt}

{"오류코드 정보:\n"+trouble_txt if trouble_txt else ""}

{"능동 제안 후보:\n"+proactive if proactive else ""}

위 정보를 바탕으로, 단계형으로 간결히 답변해라. 경고가 있으면 최상단에 '⚠️ 주의'로 강조해라.
"""
    resp = _model.generate_content(prompt)
    return {
        "answer": resp.text,
        "proactive": proactive,
        "trouble": trouble_txt,
        "used_llm": True
    }
