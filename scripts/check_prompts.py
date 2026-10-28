#!/usr/bin/env python3
"""Guard the shipped prompt list.

prompts.json is the list the capture page loads. Edit that file, then update
the expected lists here if the change is intentional. The Pages workflow runs
this script.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "prompts.json"

CONSONANTS = list("กขคงจฉชซดตถทนบปผฝพฟภมยรลวสหอ")
EXCLUDED = set("ฃฅฆฌญฎฏฐฑฒณธศษฬฮ")
THAI_DIGITS = set("๐๑๒๓๔๕๖๗๘๙")
VOWELS = [
    "\u0e2d\u0e32",  # อา
    "\u0e2d\u0e34",  # อิ
    "\u0e2d\u0e35",  # อี
    "\u0e2d\u0e36",  # อึ
    "\u0e2d\u0e37",  # อื
    "\u0e2d\u0e38",  # อุ
    "\u0e2d\u0e39",  # อู
    "\u0e40\u0e2d",  # เอ
    "\u0e41\u0e2d",  # แอ
    "\u0e42\u0e2d",  # โอ
    "\u0e43\u0e2d",  # ใอ
    "\u0e44\u0e2d",  # ไอ
    "\u0e2d\u0e30",  # อะ
    "\u0e2d\u0e31",  # อั
    "\u0e2d\u0e33",  # อำ
    "\u0e40\u0e2d\u0e32",  # เอา
    "\u0e40\u0e2d\u0e35\u0e22",  # เอีย
    "\u0e40\u0e2d\u0e37\u0e2d",  # เอือ
    "\u0e2d\u0e31\u0e27",  # อัว
]
TONES = ["\u0e2d\u0e48", "\u0e2d\u0e49", "\u0e2d\u0e4a", "\u0e2d\u0e4b"]  # อ่ อ้ อ๊ อ๋
WORDS = [
    "\u0e01\u0e34\u0e19",  # กิน
    "\u0e44\u0e1b",  # ไป
    "\u0e21\u0e32",  # มา
    "\u0e14\u0e35",  # ดี
    "\u0e23\u0e16",  # รถ
    "\u0e1b\u0e25\u0e32",  # ปลา
    "\u0e41\u0e21\u0e48",  # แม่
    "\u0e1e\u0e48\u0e2d",  # พ่อ
    "\u0e19\u0e33\u0e49",  # น้ำ น + sara am + mai tho
    "\u0e1a\u0e49\u0e32\u0e19",  # บ้าน
]


def fail(message: str) -> None:
    print(f"prompts.json: {message}", file=sys.stderr)
    raise SystemExit(1)


def texts_ok(kind: str, values: object, expected: list[str]) -> list[str]:
    if not isinstance(values, list):
        fail(f"{kind} is not an array")
    if values != expected:
        fail(f"{kind} mismatch: {values!r}")
    for text in values:
        if text != unicodedata.normalize("NFC", text):
            fail(f"{kind} is not NFC: {text!r}")
        if any(ch in THAI_DIGITS for ch in text):
            fail(f"Thai digit in {kind}: {text!r}")
        if any(ch in EXCLUDED for ch in text):
            fail(f"excluded consonant in {kind}: {text!r}")
    return values


def main() -> None:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON ({exc})")
    if not isinstance(data, dict):
        fail("expected an object")
    if data.get("repeats") != 3:
        fail("repeats must be 3")
    consonants = texts_ok("consonants", data.get("consonants"), CONSONANTS)
    vowels = texts_ok("vowels", data.get("vowels"), VOWELS)
    tones = texts_ok("tones", data.get("tones"), TONES)
    words = texts_ok("words", data.get("words"), WORDS)
    extra = set(data) - {"repeats", "consonants", "vowels", "tones", "words"}
    if extra:
        fail(f"unexpected keys: {sorted(extra)}")
    count = len(consonants) + len(vowels) + len(tones) + len(words)
    print(f"ok {count} prompts x {data['repeats']} = {count * data['repeats']} steps, {len(words)} words")


if __name__ == "__main__":
    main()
