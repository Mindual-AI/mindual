# src/agent/agent_init.py
# Gemini 기반 에이전트 초기화 및 질의 처리

from typing import Dict, Any, List

import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL_ID
from src.agent.system_prompt import SYSTEM_PROMPT
from src.agent.mcp_tools import search_manual, lookup_trouble, propose_next_action


# ---------- Gemini 초기화 ----------

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_model = genai.GenerativeModel(GEMINI_MODEL_ID) if GEMINI_API_KEY else None


# ---------- 헬퍼: 검색 컨텍스트 문자열 구성 ----------

def _build_context(query: str, hits: List[Dict[str, Any]]) -> str:
    """
    FAISS / manual 검색 결과(hits)를 사람이 읽기 좋은 문자열로 변환.
    hits: [{ "content": ..., "page": ..., ... }, ...]
    """
    if not hits:
        return "검색 결과 없음."

    lines: List[str] = []
    for i, h in enumerate(hits, 1):
        prefix = f"[{i}] (page {h.get('page', '?')})"
        content = h.get("content", "")
        lines.append(f"{prefix}\n{content}\n")

    return "\n".join(lines)


# ---------- 메인 엔트리: answer_query ----------

def answer_query(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload = {
      "query": "...",            # 사용자의 자연어 질문
      "device_state": {...},     # 선택: 현재 디바이스 상태 정보
      "error_code": "E05"        # 선택: 오류 코드
    }

    반환:
    {
      "answer": str,       # LLM 또는 컨텍스트 기반 응답
      "proactive": str?,   # 능동 제안 텍스트(있다면)
      "trouble": str?,     # 오류 코드 설명(있다면)
      "used_llm": bool     # LLM 사용 여부
    }
    """

    query = (payload.get("query") or "").strip()
    device_state = payload.get("device_state") or {}
    error_code = payload.get("error_code")

    # 1) 능동 제안 (간단 규칙 기반)
    proactive: str | None = propose_next_action(device_state) if device_state else None

    # 2) 오류 코드가 있으면 관련 트러블슈팅 먼저 조회
    trouble_txt: str | None = None
    if error_code:
        t = lookup_trouble(error_code)
        if t:
            trouble_txt = (
                f"[{error_code}] 증상: {t.get('symptom', '')}\n"
                f"원인: {t.get('cause', '')}"
            )

    # 3) 매뉴얼 검색: 질문이 있으면 질문으로, 없으면 오류코드/기본 사용으로
    search_query = query if query else (error_code or "기본 사용")
    hits = search_manual(search_query)
    context_txt = _build_context(search_query, hits)

    # 4) LLM이 없는 경우: 검색 결과만 그대로 반환
    if not _model:
        return {
            "answer": context_txt,
            "proactive": proactive,
            "trouble": trouble_txt,
            "used_llm": False,
        }

    # 5) 프롬프트 구성 (f-string 대신 리스트로 안전하게 조립)
    prompt_parts: List[str] = []

    # 시스템 프롬프트
    prompt_parts.append(SYSTEM_PROMPT)
    prompt_parts.append("")  # 빈 줄

    # 사용자 질문
    prompt_parts.append("사용자 질문:")
    prompt_parts.append(query or error_code or "질문 없음")
    prompt_parts.append("")

    # 검색 컨텍스트
    prompt_parts.append("검색 컨텍스트(매뉴얼 발췌):")
    prompt_parts.append(context_txt)
    prompt_parts.append("")

    # 오류 코드 정보
    if trouble_txt:
        prompt_parts.append("오류코드 정보:")
        prompt_parts.append(trouble_txt)
        prompt_parts.append("")

    # 능동 제안
    if proactive:
        prompt_parts.append("능동 제안 후보:")
        prompt_parts.append(proactive)
        prompt_parts.append("")

    # 출력 형식 가이드
    prompt_parts.append(
        "위 정보를 바탕으로, 단계형으로 간결히 답변해라. "
        "경고가 있으면 최상단에 '⚠️ 주의'로 강조해라."
    )

    prompt = "\n".join(prompt_parts)

    # 6) Gemini 호출
    resp = _model.generate_content(prompt)
    answer_text = getattr(resp, "text", None) or "응답 생성에 실패했습니다."

    return {
        "answer": answer_text,
        "proactive": proactive,
        "trouble": trouble_txt,
        "used_llm": True,
    }
