#!/usr/bin/env python3
"""Build prompts.json: 300 items, {id, text, kind}.

Symbols come first (consonants, vowels, tones, marks, digits), then words.
Word order keeps a required coverage set, then alphabet exemplar words,
then common words until the file is exactly 300 prompts.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prompts.json"
TARGET = 300


def C(*codes: int) -> str:
    return "".join(chr(c) for c in codes)


def nfc(text: str) -> str:
    text = unicodedata.normalize("NFC", text.strip())
    # Sara am is not a combining mark, so NFC will not reorder
    # a tone typed before it. Canonical clusters are น + ำ + ้.
    chars = list(text)
    tones = set("่้๊๋")
    out: list[str] = []
    i = 0
    while i < len(chars):
        if chars[i] in tones and i + 1 < len(chars) and chars[i + 1] == "ำ":
            out.append("ำ")
            out.append(chars[i])
            i += 2
            continue
        out.append(chars[i])
        i += 1
    return "".join(out)


CONSONANTS = [
    ("consonant-ko-kai", "ก", "ko kai"),
    ("consonant-kho-khai", "ข", "kho khai"),
    ("consonant-kho-khuat", "ฃ", "kho khuat"),
    ("consonant-kho-khwai", "ค", "kho khwai"),
    ("consonant-kho-khon", "ฅ", "kho khon"),
    ("consonant-kho-rakhang", "ฆ", "kho rakhang"),
    ("consonant-ngo-ngu", "ง", "ngo ngu"),
    ("consonant-cho-chan", "จ", "cho chan"),
    ("consonant-cho-ching", "ฉ", "cho ching"),
    ("consonant-cho-chang", "ช", "cho chang"),
    ("consonant-so-so", "ซ", "so so"),
    ("consonant-cho-choe", "ฌ", "cho choe"),
    ("consonant-yo-ying", "ญ", "yo ying"),
    ("consonant-do-chada", "ฎ", "do chada"),
    ("consonant-to-patak", "ฏ", "to patak"),
    ("consonant-tho-than", "ฐ", "tho than"),
    ("consonant-tho-nangmontho", "ฑ", "tho nangmontho"),
    ("consonant-tho-phuthao", "ฒ", "tho phuthao"),
    ("consonant-no-nen", "ณ", "no nen"),
    ("consonant-do-dek", "ด", "do dek"),
    ("consonant-to-tao", "ต", "to tao"),
    ("consonant-tho-thung", "ถ", "tho thung"),
    ("consonant-tho-thahan", "ท", "tho thahan"),
    ("consonant-tho-thong", "ธ", "tho thong"),
    ("consonant-no-nu", "น", "no nu"),
    ("consonant-bo-baimai", "บ", "bo baimai"),
    ("consonant-po-pla", "ป", "po pla"),
    ("consonant-pho-phung", "ผ", "pho phung"),
    ("consonant-fo-fa", "ฝ", "fo fa"),
    ("consonant-pho-phan", "พ", "pho phan"),
    ("consonant-fo-fan", "ฟ", "fo fan"),
    ("consonant-pho-samphao", "ภ", "pho samphao"),
    ("consonant-mo-ma", "ม", "mo ma"),
    ("consonant-yo-yak", "ย", "yo yak"),
    ("consonant-ro-ruea", "ร", "ro ruea"),
    ("consonant-lo-ling", "ล", "lo ling"),
    ("consonant-wo-waen", "ว", "wo waen"),
    ("consonant-so-sala", "ศ", "so sala"),
    ("consonant-so-ruesi", "ษ", "so ruesi"),
    ("consonant-so-suea", "ส", "so suea"),
    ("consonant-ho-hip", "ห", "ho hip"),
    ("consonant-lo-chula", "ฬ", "lo chula"),
    ("consonant-o-ang", "อ", "o ang"),
    ("consonant-ho-nokhuk", "ฮ", "ho nokhuk"),
]

# (id, typed Thai, codepoints). The typed form must match the codepoints.
VOWELS = [
    ("vowel-sara-a", "อะ", C(0x0E2D, 0x0E30)),
    ("vowel-sara-aa", "อา", C(0x0E2D, 0x0E32)),
    ("vowel-mai-han-akat", "อั", C(0x0E2D, 0x0E31)),
    ("vowel-sara-i", "อิ", C(0x0E2D, 0x0E34)),
    ("vowel-sara-ii", "อี", C(0x0E2D, 0x0E35)),
    ("vowel-sara-ue", "อึ", C(0x0E2D, 0x0E36)),
    ("vowel-sara-uee", "อือ", C(0x0E2D, 0x0E37, 0x0E2D)),
    ("vowel-sara-u", "อุ", C(0x0E2D, 0x0E38)),
    ("vowel-sara-uu", "อู", C(0x0E2D, 0x0E39)),
    ("vowel-sara-e", "เอ", C(0x0E40, 0x0E2D)),
    ("vowel-sara-e-short", "เอะ", C(0x0E40, 0x0E2D, 0x0E30)),
    ("vowel-sara-ae", "แอ", C(0x0E41, 0x0E2D)),
    ("vowel-sara-ae-short", "แอะ", C(0x0E41, 0x0E2D, 0x0E30)),
    ("vowel-sara-o", "โอ", C(0x0E42, 0x0E2D)),
    ("vowel-sara-o-short", "โอะ", C(0x0E42, 0x0E2D, 0x0E30)),
    ("vowel-sara-o-ang", "ออ", C(0x0E2D, 0x0E2D)),
    ("vowel-sara-o-ang-short", "เอาะ", C(0x0E40, 0x0E2D, 0x0E32, 0x0E30)),
    ("vowel-sara-oe", "เออ", C(0x0E40, 0x0E2D, 0x0E2D)),
    ("vowel-sara-oe-short", "เออะ", C(0x0E40, 0x0E2D, 0x0E2D, 0x0E30)),
    ("vowel-sara-ia", "เอีย", C(0x0E40, 0x0E2D, 0x0E35, 0x0E22)),
    ("vowel-sara-ia-short", "เอียะ", C(0x0E40, 0x0E2D, 0x0E35, 0x0E22, 0x0E30)),
    ("vowel-sara-uea", "เอือ", C(0x0E40, 0x0E2D, 0x0E37, 0x0E2D)),
    ("vowel-sara-uea-short", "เอือะ", C(0x0E40, 0x0E2D, 0x0E37, 0x0E2D, 0x0E30)),
    ("vowel-sara-ua", "อัว", C(0x0E2D, 0x0E31, 0x0E27)),
    ("vowel-sara-ua-short", "อัวะ", C(0x0E2D, 0x0E31, 0x0E27, 0x0E30)),
    ("vowel-sara-ai-maimuan", "ใอ", C(0x0E43, 0x0E2D)),
    ("vowel-sara-ai-maimalai", "ไอ", C(0x0E44, 0x0E2D)),
    ("vowel-sara-am", "อำ", C(0x0E2D, 0x0E33)),
    ("vowel-sara-ao", "เอา", C(0x0E40, 0x0E2D, 0x0E32)),
    ("vowel-rue", "ฤ", C(0x0E24)),
    ("vowel-rue-long", "ฤๅ", C(0x0E24, 0x0E45)),
    ("vowel-lue", "ฦ", C(0x0E26)),
    ("vowel-lue-long", "ฦๅ", C(0x0E26, 0x0E45)),
    ("vowel-mai-taikhu", "เอ็", C(0x0E40, 0x0E2D, 0x0E47)),
]

TONES = [
    ("tone-mai-ek", "อ่", C(0x0E2D, 0x0E48)),
    ("tone-mai-tho", "อ้", C(0x0E2D, 0x0E49)),
    ("tone-mai-tri", "อ๊", C(0x0E2D, 0x0E4A)),
    ("tone-mai-chattawa", "อ๋", C(0x0E2D, 0x0E4B)),
]

MARKS = [
    ("mark-thanthakhat", "อ์", C(0x0E2D, 0x0E4C)),
    ("mark-maiyamok", "ๆ", C(0x0E46)),
    ("mark-paiyannoi", "ฯ", C(0x0E2F)),
    ("mark-paiyannoi-la", "ฯลฯ", C(0x0E2F, 0x0E25, 0x0E2F)),
]

# Coverage words are never dropped. They exercise every vowel position,
# stacked vowel+tone marks, and the examples named in the project brief.
REQUIRED_WORDS = [
    "กิน",
    "เพื่อน",
    "เที่ยว",
    "ไม่",
    "น้ำ",
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
]

# Traditional names of the 44 consonants, as ordinary words.
EXEMPLARS = [
    "ไก่",
    "ไข่",
    "ขวด",
    "ควาย",
    "คน",
    "ระฆัง",
    "งู",
    "จาน",
    "ฉิ่ง",
    "ช้าง",
    "โซ่",
    "เฌอ",
    "หญิง",
    "ชฎา",
    "ปฏัก",
    "ฐาน",
    "นางมณโฑ",
    "ผู้เฒ่า",
    "เณร",
    "เด็ก",
    "เต่า",
    "ถุง",
    "ทหาร",
    "ธง",
    "หนู",
    "ใบไม้",
    "ปลา",
    "ผึ้ง",
    "ฝา",
    "พาน",
    "ฟัน",
    "สำเภา",
    "ม้า",
    "ยักษ์",
    "เรือ",
    "ลิง",
    "แหวน",
    "ศาลา",
    "ฤๅษี",
    "เสือ",
    "หีบ",
    "จุฬา",
    "อ่าง",
    "นกฮูก",
]

# Earlier entries are kept first. The builder stops at 300 prompts,
# so the least important function words sit at the end.
CORE_WORDS = [
    "สวัสดี",
    "ขอบคุณ",
    "ขอโทษ",
    "สอง",
    "สาม",
    "สี่",
    "ห้า",
    "หก",
    "เจ็ด",
    "แปด",
    "เก้า",
    "สิบ",
    "วันอังคาร",
    "วันพุธ",
    "วันพฤหัสบดี",
    "วันศุกร์",
    "วันเสาร์",
    "วันอาทิตย์",
    "ทำ",
    "รู้",
    "เขียน",
    "อ่าน",
    "พูด",
    "เดิน",
    "วิ่ง",
    "นั่ง",
    "นอน",
    "เปิด",
    "ปิด",
    "ซื้อ",
    "ขาย",
    "เรียน",
    "สอน",
    "เล่น",
    "ฟัง",
    "ใช้",
    "หา",
    "รัก",
    "ชอบ",
    "ช่วย",
    "รอ",
    "เจอ",
    "เข้า",
    "ออก",
    "ขึ้น",
    "ลง",
    "กลับ",
    "เริ่ม",
    "จบ",
    "ถาม",
    "ตอบ",
    "คิด",
    "เข้าใจ",
    "เกิด",
    "เลือก",
    "ใหม่",
    "เก่า",
    "ใหญ่",
    "เล็ก",
    "สวย",
    "ร้อน",
    "เร็ว",
    "ช้า",
    "ใกล้",
    "ไกล",
    "สูง",
    "ต่ำ",
    "ง่าย",
    "ยาก",
    "แพง",
    "แดง",
    "เขียว",
    "เหลือง",
    "ขาว",
    "ดำ",
    "ไม้",
    "ไข้",
    "เก๋",
    "ก๋ง",
    "เอ๋",
    "เก๊",
    "เดี๋ยว",
    "เสื้อ",
    "เกลือ",
    "เหลือ",
    "เชื่อ",
    "กลัว",
    "รวม",
    "ข่าว",
    "ดาว",
    "เรา",
    "เลี้ยง",
    "เปลี่ยน",
    "เสียง",
    "เดียว",
    "เปรี้ยว",
    "เทียน",
    "พ่อ",
    "ลูก",
    "พี่",
    "น้อง",
    "ปู่",
    "ย่า",
    "ตา",
    "ยาย",
    "ลุง",
    "ป้า",
    "ครู",
    "หมอ",
    "ชื่อ",
    "เด็กๆ",
    "ผู้หญิง",
    "ผู้ชาย",
    "ครอบครัว",
    "คนไทย",
    "ข้าว",
    "อาหาร",
    "ขนม",
    "ผลไม้",
    "หมู",
    "เนื้อ",
    "ผัก",
    "นม",
    "ชา",
    "กาแฟ",
    "หวาน",
    "เผ็ด",
    "อร่อย",
    "ช้อน",
    "ส้อม",
    "ถ้วย",
    "โจ๊ก",
    "ขนมปัง",
    "ผัดไทย",
    "ส้มตำ",
    "ต้มยำ",
    "ข้าวผัด",
    "แกงเขียวหวาน",
    "น้ำเปล่า",
    "หู",
    "ปาก",
    "ขา",
    "แขน",
    "ผม",
    "นิ้ว",
    "บ้าน",
    "ห้อง",
    "เมือง",
    "ประเทศ",
    "ไทย",
    "โรงเรียน",
    "ตลาด",
    "ถนน",
    "วัด",
    "สวน",
    "ทะเล",
    "ภูเขา",
    "กรุงเทพ",
    "ประเทศไทย",
    "เวลา",
    "เดือน",
    "ปี",
    "เช้า",
    "เย็น",
    "วันนี้",
    "พรุ่งนี้",
    "เมื่อวาน",
    "นาฬิกา",
    "รถ",
    "ไฟ",
    "ไหน",
    "ใส่",
    "ไฟฟ้า",
    "เงิน",
    "บาท",
    "งาน",
    "หนังสือ",
    "กระดาษ",
    "ปากกา",
    "ดินสอ",
    "ภาษา",
    "เก้าอี้",
    "นักเรียน",
    "โทรศัพท์",
    "คอมพิวเตอร์",
    "อินเทอร์เน็ต",
    "ไปรษณีย์",
    "สิทธิ์",
    "ฤทธิ์",
    "ฝน",
    "ฤดู",
    "สุข",
    "หยุด",
    "ใน",
    "ให้",
    "ไป",
    "แล้ว",
    "ก็",
    "คือ",
    "ว่า",
    "ของ",
    "แต่",
    "กับ",
    "จาก",
    "โดย",
    "ถ้า",
    "เพราะ",
    "เมื่อ",
    "อยู่",
    "ยัง",
    "กว่า",
    "มาก",
    "ถูก",
    "ต้อง",
    "อีก",
    "ทุก",
    "ด้วย",
    "ค่ะ",
    "ครับ",
    "นี้",
    "นั้น",
    "หรือ",
    "นะ",
    "อย่างไร",
    "ทำไม",
    "อะไร",
    "ที่ไหน",
    "เมื่อไร",
    "บาง",
    "ทั้ง",
    "เช่น",
    "ซึ่ง",
    "เอง",
]


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        text = nfc(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def item(pid: str, text: str, kind: str) -> dict:
    return {"id": pid, "text": nfc(text), "kind": kind}


def main() -> None:
    for pid, typed, built in VOWELS + TONES + MARKS:
        if nfc(typed) != built:
            raise SystemExit(f"{pid} typed {typed!r} != codepoints {built!r}")

    prompts: list[dict] = []
    for pid, text, _name in CONSONANTS:
        prompts.append(item(pid, text, "consonant"))
    for pid, text, _built in VOWELS:
        prompts.append(item(pid, text, "vowel"))
    for pid, text, _built in TONES:
        prompts.append(item(pid, text, "tone"))
    for pid, text, _built in MARKS:
        prompts.append(item(pid, text, "mark"))
    thai_digits = "๐๑๒๓๔๕๖๗๘๙"
    for i, ch in enumerate(thai_digits):
        prompts.append(item(f"digit-thai-{i}", ch, "digit"))
    for i in range(10):
        prompts.append(item(f"digit-arabic-{i}", str(i), "digit"))

    must = dedupe(REQUIRED_WORDS + EXEMPLARS)
    rest = [w for w in dedupe(CORE_WORDS) if w not in set(must)]
    need = TARGET - len(prompts) - len(must)
    if need < 0:
        raise SystemExit(f"required words overflow target by {-need}")
    if len(rest) < need:
        raise SystemExit(f"need {need} more words, have {len(rest)}")
    words = must + rest[:need]
    for n, text in enumerate(words, start=1):
        prompts.append(item(f"word-{n:03d}", text, "word"))

    if len(prompts) != TARGET:
        raise SystemExit(f"expected {TARGET}, got {len(prompts)}")

    ids = [p["id"] for p in prompts]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate ids")
    texts = [p["text"] for p in prompts]
    if len(texts) != len(set(texts)):
        dupes = sorted({t for t in texts if texts.count(t) > 1})
        raise SystemExit(f"duplicate texts: {dupes}")

    OUT.write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for p in prompts:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"wrote {OUT} ({len(prompts)} prompts)")
    print(kinds)


if __name__ == "__main__":
    main()
