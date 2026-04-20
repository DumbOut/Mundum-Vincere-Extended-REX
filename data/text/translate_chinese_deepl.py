import os
import re
import requests
import time

# =========================
# CONFIG
# =========================
API_KEY = "YOUR_DEEPL_API_KEY"
INPUT_DIR = "input_txts"
OUTPUT_DIR = "output_txts"
TARGET_LANG = "ZH"   # e.g. ZH, ES, FR, DE
CHUNK_SIZE = 4000    # safe chunk size

DEEPL_URL = "https://api-free.deepl.com/v2/translate"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# HELPERS
# =========================
def is_key_line(line):
    return line.strip().startswith("{") and "}" in line

def chunk_text(text, size):
    return [text[i:i+size] for i in range(0, len(text), size)]

def translate_text(text):
    chunks = chunk_text(text, CHUNK_SIZE)
    translated = []

    for chunk in chunks:
        response = requests.post(
            DEEPL_URL,
            data={
                "auth_key": API_KEY,
                "text": chunk,
                "target_lang": TARGET_LANG
            }
        )

        if response.status_code != 200:
            print("Error:", response.text)
            return text

        translated.append(response.json()["translations"][0]["text"])
        time.sleep(0.2)  # avoid rate limit

    return "".join(translated)

# =========================
# MAIN
# =========================
for file in os.listdir(INPUT_DIR):
    if not file.endswith(".txt"):
        continue

    input_path = os.path.join(INPUT_DIR, file)
    output_path = os.path.join(OUTPUT_DIR, file)

    print(f"Processing: {file}")

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    buffer = []

    for line in lines:
        if is_key_line(line):
            # flush buffer before key
            if buffer:
                joined = "".join(buffer)
                translated = translate_text(joined)
                new_lines.append(translated)
                buffer = []
            new_lines.append(line)
        else:
            buffer.append(line)

    # final flush
    if buffer:
        joined = "".join(buffer)
        translated = translate_text(joined)
        new_lines.append(translated)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"Done: {file}")

print("ALL FILES DONE")