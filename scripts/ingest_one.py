# scripts/ingest_one.py
# PDF 1개 OCR→파싱→DB적재 파이프라인
"""
Ingest one manual PDF into the SQLite RAG DB.
"""

import argparse
import json
import os
import re
import sqlite3
import time
import random
from pathlib import Path
from typing import List

from PIL import Image
import google.generativeai as genai

# ========= Project imports =========
from src.config import GEMINI_API_KEY, GEMINI_MODEL_ID, DB_PATH
from db.upsert import upsert_manual, insert_chunk


# ---------- PDF -> image ----------
try:
    import pypdfium2 as pdfium
    USE_PDFIUM = True
except Exception:
    from pdf2image import convert_from_path
    USE_PDFIUM = False


def render_pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 200) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    img_paths: List[Path] = []
    if USE_PDFIUM:
        pdf = pdfium.PdfDocument(str(pdf_path))
        for i, page in enumerate(pdf):
            pil_image = page.render(scale=dpi / 72).to_pil()
            p = out_dir / f"page_{i+1}.jpg"
            pil_image.save(p, "JPEG")
            img_paths.append(p)
    else:
        pages = convert_from_path(str(pdf_path), dpi=dpi)
        for i, page in enumerate(pages, start=1):
            p = out_dir / f"page_{i}.jpg"
            page.save(p, "JPEG")
            img_paths.append(p)
    print(f"✅ Rendered {len(img_paths)} pages -> {out_dir}")
    return img_paths


# ---------- Gemini setup ----------
def setup_gemini():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set. Put it in .env")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL_ID)


# ---------- Retry helper ----------
def retry_with_backoff(fn, *, retries=6, base=1.5, jitter=0.3, on_msg=""):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if "Resource exhausted" in msg or "429" in msg or "exceeded" in msg:
                sleep = (base ** attempt) + random.uniform(0, jitter)
                print(f"⏳ {on_msg} 재시도 {attempt+1}/{retries} ... {sleep:.1f}s 대기 (사유: {msg[:80]}...)")
                time.sleep(sleep)
                continue
            raise
    raise RuntimeError(f"재시도 초과: {on_msg}")


# ---------- OCR ----------
DEFAULT_PER_PAGE_SLEEP = 1.2
SKIP_IF_EXISTS = True

def ocr_image(model, img_path: Path) -> str:
    image = Image.open(img_path)
    prompt = (
        "이 이미지는 전자기기 사용설명서의 한 페이지입니다. "
        "보이는 모든 텍스트를 가능한 정확도로 추출해 주세요. "
        "줄바꿈과 리스트, 표 구조(가능하면 마크다운 테이블)를 보존해 주세요."
    )
    def _call():
        return model.generate_content([prompt, image])
    resp = retry_with_backoff(_call, on_msg=f"OCR {img_path.name}")
    return resp.text or ""


def ocr_images_to_texts(model, img_paths: List[Path], out_dir: Path,
                        per_page_sleep: float = DEFAULT_PER_PAGE_SLEEP,
                        start_page: int = 1, end_page: int | None = None) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_paths: List[Path] = []
    total = len(img_paths)
    for idx, img in enumerate(img_paths, start=1):
        if idx < start_page:
            continue
        if end_page and idx > end_page:
            break

        txt_path = out_dir / (img.stem + ".txt")
        if SKIP_IF_EXISTS and txt_path.exists() and txt_path.stat().st_size > 10:
            txt_paths.append(txt_path)
            continue

        print(f"🔎 OCR {idx}/{total} : {img.name}")
        text = ocr_image(model, img)
        txt_path.write_text(text, encoding="utf-8")
        txt_paths.append(txt_path)

        if per_page_sleep > 0:
            time.sleep(per_page_sleep)
    print(f"✅ OCR saved {len(txt_paths)} text files -> {out_dir}")
    return txt_paths


# ---------- Merge ----------
def merge_texts(txt_paths: List[Path], merged_path: Path) -> None:
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    parts = [p.read_text(encoding="utf-8") for p in txt_paths]
    merged_path.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"✅ Merged text -> {merged_path}")


# ---------- Meta helpers ----------
def infer_meta_from_filename(stem: str):
    tokens = re.split(r"[^A-Za-z0-9\-]+", stem)
    models = [t for t in tokens if re.search(r"[A-Za-z]{2,}\d{2,}", t)]
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", stem)
    created_at = m.group(1) if m else ""
    return list(dict.fromkeys(models)), created_at


# ---------- DB utilities ----------
def ensure_fts_sync(conn: sqlite3.Connection):
    conn.execute("""
        INSERT INTO chunks_fts(rowid, content)
        SELECT id, content FROM chunks
        WHERE id NOT IN (SELECT rowid FROM chunks_fts);
    """)
    conn.commit()


# ---------- Main pipeline ----------
def ingest_one(pdf_path: Path, brand: str, language: str, title: str,
               dpi: int = 200, clean: bool = False,
               start_page: int = 1, end_page: int | None = None,
               per_page_sleep: float = DEFAULT_PER_PAGE_SLEEP):
    stem = pdf_path.stem
    interim_dir = Path("data/interim") / stem
    processed_dir = Path("data/processed") / stem

    if clean:
        for d in [interim_dir, processed_dir]:
            if d.exists():
                for p in d.glob("*"):
                    p.unlink()

    img_paths = render_pdf_to_images(pdf_path, interim_dir, dpi=dpi)

    model = setup_gemini()
    txt_paths = ocr_images_to_texts(model, img_paths, processed_dir,
                                    per_page_sleep=per_page_sleep,
                                    start_page=start_page, end_page=end_page)

    merged_path = processed_dir / "merged_manual.txt"
    merge_texts(txt_paths, merged_path)

    models, created_at = infer_meta_from_filename(stem)
    manual_id = upsert_manual(
        file_name=pdf_path.name,
        model_list=models or [],
        language=language,
        title=title or stem,
        created_at=created_at or ""
    )
    print(f"✅ Upserted manual id={manual_id} models={models} created_at={created_at}")

    for i, txt_path in enumerate(txt_paths, start=1):
        content = txt_path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        meta = {"type": "page", "source": "ocr", "file": pdf_path.name}
        insert_chunk(manual_id=manual_id, section_id=None, page=i, content=content, meta=meta)

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_fts_sync(conn)
    finally:
        conn.close()

    print("🎉 Ingestion complete.")
    print(f"   - Manual ID: {manual_id}")
    print(f"   - Pages ingested: {len(txt_paths)}")
    print(f"   - DB: {DB_PATH}")


def main():
    ap = argparse.ArgumentParser(description="Ingest one manual PDF into DB")
    ap.add_argument("--pdf", required=True, help="Path to the PDF file")
    ap.add_argument("--brand", default="", help="Brand name (optional)")
    ap.add_argument("--language", default="ko", help="Manual language code")
    ap.add_argument("--title", default="", help="Manual title")
    ap.add_argument("--dpi", type=int, default=200, help="Render DPI")
    ap.add_argument("--clean", action="store_true", help="Clean existing interim/processed files")
    ap.add_argument("--start", type=int, default=1, help="시작 페이지(1-base)")
    ap.add_argument("--end", type=int, default=0, help="끝 페이지(포함). 0은 전체")
    ap.add_argument("--sleep", type=float, default=DEFAULT_PER_PAGE_SLEEP, help="페이지당 대기(초)")
    args = ap.parse_args()

    end_page = args.end if args.end > 0 else None
    ingest_one(pdf_path=Path(args.pdf),
               brand=args.brand,
               language=args.language,
               title=args.title,
               dpi=args.dpi,
               clean=args.clean,
               start_page=args.start,
               end_page=end_page,
               per_page_sleep=args.sleep)


if __name__ == "__main__":
    main()
