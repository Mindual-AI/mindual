# src/config.py
# 경로/환경변수 로딩
import os
from dotenv import load_dotenv

load_dotenv()

# DB 경로
DB_PATH = os.getenv("DB_PATH", "./manuals.sqlite")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-2.0-flash")

# 검색 기본 파라미터
RAG_MAX_DOCS = int(os.getenv("RAG_MAX_DOCS", "5"))
