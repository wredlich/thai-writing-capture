#!/usr/bin/env python3
"""Guard the shipped prompt list.

If you replace prompts.json, update the witness list in this file or the
Pages workflow will fail the deploy.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "prompts.json"

KINDS = {"consonant", "vowel", "tone", "mark", "digit", "word"}
CONSONANTS = list("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")
THAI_DIGITS = list("๐๑๒๓๔๕๖๗๘๙")
ARABIC_DIGITS = list("0123456789")

# These strings must appear as whole prompt texts.
WITNESS_TEXTS = [
    "กิน",
    "เพื่อน",
    "เที่ยว",
    "ไม่",
    "\u0e19\u0e33\u0e49",  # น้ำ: น + sara am + mai tho
    "ใคร",
    "ก๋วยเตี๋ยว",
    "มี",
    "ถึง",
    "มือ",
    "คุณ",
    "ดู",
    "เก่ง",
    "แม่",
    "โลก",
    "ใจ",
    "ได้",
    "มา",
    "จะ",
    "วัน",
    "เป็น",
    "เขา",
    "เธอ",
    "เกาะ",
    "ตัว",
    "ที่",
    "ก๊อก",
    "ต่างๆ",
    "วันจันทร์",
    "ยักษ์",
    "หนึ่ง",
    "โต๊ะ",
    "และ",
    "อ่",
    "อ้",
    "อ๊",
    "อ๋",
    "อ์",
    "ๆ",
    "ฯ",
    "ฤ",
    "ฤๅ",
    "ฦ",
    "ฦๅ",
    "อิ",
    "อี",
    "อุ",
    "อู",
    "เอ",
    "แอ",
    "โอ",
    "ใอ",
    "ไอ",
    "อำ",
]

# Vowel-position codepoints that must show up inside a word, not only in isolation.
WORD_CODEPOINTS = {
    "above sara i": "\u0e34",
    "above sara ii": "\u0e35",
    "above sara ue": "\u0e36",
    "above sara uee": "\u0e37",
    "below sara u": "\u0e38",
    "below sara uu": "\u0e39",
    "leading sara e": "\u0e40",
    "leading sara ae": "\u0e41",
    "leading sara o": "\u0e42",
    "leading sara ai maimuan": "\u0e43",
    "leading sara ai maimalai": "\u0e44",
    "trailing sara a": "\u0e30",
    "trailing sara aa": "\u0e32",
    "sara am": "\u0e33",
    "mai han-akat": "\u0e31",
    "mai taikhu": "\u0e47",
    "tone mai ek": "\u0e48",
    "tone mai tho": "\u0e49",
    "tone mai tri": "\u0e4a",
    "tone mai chattawa": "\u0e4b",
    "thanthakhat": "\u0e4c",
    "maiyamok": "\u0e46",
}


def fail(message: str) -> None:
    print(f"prompts.json: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON ({exc})")
    if not isinstance(data, list) or not data:
        fail("expected a non-empty array")

    ids: list[str] = []
    texts: list[str] = []
    consonants: list[str] = []
    words: list[str] = []
    digits: list[str] = []

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            fail(f"item {index} is not an object")
        if set(item) != {"id", "text", "kind"}:
            fail(f"item {index} keys are {sorted(item)}; expected id, text, kind")
        pid = item["id"]
        text = item["text"]
        kind = item["kind"]
        if not isinstance(pid, str) or not pid or any(c.isspace() for c in pid):
            fail(f"bad id at {index}: {pid!r}")
        if not isinstance(text, str) or text != unicodedata.normalize("NFC", text).strip() or not text:
            fail(f"bad text at {index}: {text!r}")
        if kind not in KINDS:
            fail(f"bad kind {kind!r} at {index}")
        if kind == "digit":
            if text not in THAI_DIGITS and text not in ARABIC_DIGITS:
                fail(f"bad digit {text!r}")
        elif any(not ("\u0e00" <= ch <= "\u0e7f") for ch in text):
            fail(f"non-Thai text in {kind} {text!r}")
        ids.append(pid)
        texts.append(text)
        if kind == "consonant":
            consonants.append(text)
        elif kind == "word":
            words.append(text)
        elif kind == "digit":
            digits.append(text)

    if len(ids) != len(set(ids)):
        fail("duplicate ids")
    if len(texts) != len(set(texts)):
        fail("duplicate texts")
    if consonants != CONSONANTS:
        fail(f"consonants are not the 44 letters in order: {''.join(consonants)}")
    if digits != THAI_DIGITS + ARABIC_DIGITS:
        fail(f"digits mismatch: {digits}")

    text_set = set(texts)
    missing = [t for t in WITNESS_TEXTS if t not in text_set]
    if missing:
        fail(f"missing witness prompts: {missing}")

    blob = "\n".join(words)
    missing_pos = [name for name, ch in WORD_CODEPOINTS.items() if ch not in blob]
    if missing_pos:
        fail(f"words do not cover: {missing_pos}")

    # Stacked vowel sign + tone (น้ำ, ที่, เพื่อน, หนึ่ง, ก๋วยเตี๋ยว).
    vowels = set("ิีึืุูั็ำ")
    tones = set("่้๊๋")
    stacked = False
    for word in words:
        chars = list(word)
        for i, ch in enumerate(chars):
            if ch not in tones:
                continue
            prev = chars[i - 1] if i else ""
            if prev in vowels or prev == "ำ":
                stacked = True
                break
        if stacked:
            break
    if not stacked:
        fail("no word stacks a vowel sign with a tone mark")

    bad_follow = set("ิีึืุูั็ำ")
    for text in texts:
        chars = list(text)
        for i, ch in enumerate(chars[:-1]):
            if ch in tones and chars[i + 1] in bad_follow:
                fail(f"tone mark sits before a vowel sign in {text!r}")

    if not (250 <= len(data) <= 400):
        fail(f"unexpected length {len(data)}")

    print(f"ok {len(data)} prompts, {len(words)} words")


if __name__ == "__main__":
    main()
