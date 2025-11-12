# src/parse/parse_text.py
# OCR 결과 → 구조화
import os

def merge_ocr_text(input_folder="data/processed", output_file="data/processed/merged_manual.txt"):
    texts = []
    for fname in sorted(os.listdir(input_folder)):
        if fname.endswith(".txt"):
            with open(os.path.join(input_folder, fname), encoding="utf-8") as f:
                texts.append(f.read().strip())
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(texts))
    print(f"✅ Merged OCR text saved: {output_file}")
