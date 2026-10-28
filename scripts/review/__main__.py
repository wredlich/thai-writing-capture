"""Review a Write Echo JSON export.

Reads the file downloaded from the admin page. Does not connect to Supabase
and does not use a service key.

Keeps the newest sample for each writer, prompt, and repetition. Flags
near-empty ink, scribbles and overfilled boxes, strokes that are much too
fast or too slow, unusual stroke counts, and shapes that sit far from other
writers on the same prompt. Writes an index plus one HTML page per prompt.
Thumbnails are grouped and labelled by invite label.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

RESAMPLE_N = 32
OUTLIER_MIN_WRITERS = 5
DROP_FRACTION = 0.5
DROP_MIN_KEPT = 3
NEAR_EMPTY_POINTS = 8
NEAR_EMPTY_PATH = 24
SCRIBBLE_PATH_DIAGONALS = 6
TOO_FAST_MS = 180
TOO_FAST_PX_PER_MS = 2.2
TOO_SLOW_MS = 30000
ABNORMAL_MIN_SAMPLES = 8
ABNORMAL_ABSOLUTE = 20


def load_export(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("export must be a JSON object")
    writers = data.get("writers") or []
    samples = data.get("samples") or []
    invites = data.get("invites") or []
    if not isinstance(writers, list) or not isinstance(samples, list):
        raise SystemExit("export needs writers and samples arrays")
    if not isinstance(invites, list):
        invites = []
    return {"writers": writers, "samples": samples, "invites": invites}


def invite_labels(invites: list) -> dict:
    labels = {}
    for row in invites:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        if code:
            labels[code] = row
    return labels


def label_for(writer: dict, invites: dict) -> str:
    code = str(writer.get("invite_code") or "").strip()
    if not code:
        return "No invite"
    row = invites.get(code)
    if not row:
        return code
    label = str(row.get("label") or "").strip()
    return label or code


def _num(value, default=0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def parse_strokes(sample: dict) -> list:
    strokes = []
    for stroke in sample.get("strokes") or []:
        if not isinstance(stroke, list):
            continue
        points = []
        for point in stroke:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                continue
            points.append((_num(point.get("x")), _num(point.get("y")), _num(point.get("t"))))
        if points:
            strokes.append(points)
    return strokes


def path_length(strokes: list) -> float:
    total = 0.0
    for stroke in strokes:
        for i in range(1, len(stroke)):
            total += math.hypot(stroke[i][0] - stroke[i - 1][0], stroke[i][1] - stroke[i - 1][1])
    return total


def duration_ms(strokes: list) -> float:
    times = [point[2] for stroke in strokes for point in stroke]
    if len(times) < 2:
        return 0.0
    return max(times) - min(times)


def bbox(strokes: list):
    xs = [point[0] for stroke in strokes for point in stroke]
    ys = [point[1] for stroke in strokes for point in stroke]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def canvas_of(sample: dict, strokes: list):
    width = _num(sample.get("canvas_w"))
    height = _num(sample.get("canvas_h"))
    if width >= 2 and height >= 2:
        return width, height
    min_x, min_y, max_x, max_y = bbox(strokes)
    return max(max_x - min_x, 1.0), max(max_y - min_y, 1.0)


def point_count(strokes: list) -> int:
    return sum(len(stroke) for stroke in strokes)


def resample(points: list, count: int = RESAMPLE_N) -> list:
    if not points:
        return []
    if len(points) == 1 or count < 2:
        return [points[0][:2]] * count
    lengths = [0.0]
    for i in range(1, len(points)):
        lengths.append(lengths[-1] + math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
    total = lengths[-1]
    if total <= 0:
        return [points[0][:2]] * count
    out = []
    index = 0
    for step in range(count):
        target = total * step / (count - 1)
        while index < len(lengths) - 2 and lengths[index + 1] < target:
            index += 1
        span = lengths[index + 1] - lengths[index]
        mix = 0.0 if span == 0 else (target - lengths[index]) / span
        x = points[index][0] + (points[index + 1][0] - points[index][0]) * mix
        y = points[index][1] + (points[index + 1][1] - points[index][1]) * mix
        out.append((x, y))
    return out


def flatten(strokes: list) -> list:
    points = []
    for stroke in strokes:
        points.extend(stroke)
    return points


def normalize(points: list) -> list:
    if not points:
        return []
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    scale = max(max_x - min_x, max_y - min_y, 1e-6)
    return [((x - min_x) / scale, (y - min_y) / scale) for x, y in points]


def trajectory(strokes: list) -> list:
    return normalize(resample(flatten(strokes)))


def mean_distance(left: list, right: list) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(left, right)) / len(left)


def median_trajectory(trajs: list) -> list:
    count = len(trajs[0])
    merged = []
    for index in range(count):
        xs = sorted(traj[index][0] for traj in trajs)
        ys = sorted(traj[index][1] for traj in trajs)
        mid = len(xs) // 2
        if len(xs) % 2:
            merged.append((xs[mid], ys[mid]))
        else:
            merged.append(((xs[mid - 1] + xs[mid]) / 2, (ys[mid - 1] + ys[mid]) / 2))
    return merged


def quantile(values: list, fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = math.floor(index)
    high = min(low + 1, len(ordered) - 1)
    mix = index - low
    return ordered[low] * (1 - mix) + ordered[high] * mix


def prepare(samples: list) -> list:
    """Copy samples, fill a repetition, and mark the newest one per writer+prompt+rep."""
    grouped = defaultdict(list)
    for sample in samples:
        if isinstance(sample, dict):
            grouped[(sample.get("writer_id"), sample.get("prompt_id"))].append(dict(sample))
    prepared = []
    for group in grouped.values():
        group.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""))
        used = set()
        missing = []
        for sample in group:
            rep = sample.get("rep")
            if isinstance(rep, int) and not isinstance(rep, bool) and rep >= 1:
                sample["_rep"] = rep
                used.add(rep)
                prepared.append(sample)
            else:
                missing.append(sample)
        next_rep = 1
        for sample in missing:
            while next_rep in used:
                next_rep += 1
            sample["_rep"] = next_rep
            used.add(next_rep)
            next_rep += 1
            prepared.append(sample)
    newest = {}
    for sample in prepared:
        key = (sample.get("writer_id"), sample.get("prompt_id"), sample["_rep"])
        current = newest.get(key)
        stamp = (sample.get("created_at") or "", sample.get("id") or "")
        if current is None or stamp >= (current.get("created_at") or "", current.get("id") or ""):
            newest[key] = sample
    for sample in prepared:
        key = (sample.get("writer_id"), sample.get("prompt_id"), sample["_rep"])
        sample["_kept"] = newest[key] is sample
    return prepared


def absolute_flags(sample: dict) -> list:
    strokes = parse_strokes(sample)
    points = point_count(strokes)
    length = path_length(strokes)
    width, height = canvas_of(sample, strokes)
    diagonal = math.hypot(width, height) or 1.0
    flags = []
    short_side = min(width, height)
    near_empty = points < NEAR_EMPTY_POINTS or length < NEAR_EMPTY_PATH or length < 0.12 * short_side
    if near_empty:
        return ["near-empty"]
    strokes_n = len(strokes)
    min_x, min_y, max_x, max_y = bbox(strokes)
    area_ratio = ((max_x - min_x) * (max_y - min_y)) / (width * height) if width and height else 0
    if (
        length > SCRIBBLE_PATH_DIAGONALS * diagonal
        or (strokes_n >= 15 and length > 2.5 * diagonal)
        or (area_ratio > 0.8 and length > 2 * diagonal)
    ):
        flags.append("scribble-overfill")
    elapsed = duration_ms(strokes)
    speed = length / elapsed if elapsed > 0 else 0
    if elapsed < TOO_FAST_MS or speed > TOO_FAST_PX_PER_MS:
        flags.append("too-fast")
    if elapsed > TOO_SLOW_MS:
        flags.append("too-slow")
    sample["_strokes_n"] = strokes_n
    sample["_traj"] = trajectory(strokes) if "scribble-overfill" not in flags else None
    return flags


def add_relative_flags(samples: list) -> None:
    by_prompt = defaultdict(list)
    for sample in samples:
        if sample.get("_kept"):
            by_prompt[sample.get("prompt_id")].append(sample)
    for group in by_prompt.values():
        comparable = [sample for sample in group if "near-empty" not in sample["_flags"]]
        counts = [sample.get("_strokes_n") or len(parse_strokes(sample)) for sample in comparable]
        for sample, count in zip(comparable, counts):
            sample["_strokes_n"] = count
        if len(counts) >= ABNORMAL_MIN_SAMPLES:
            middle = statistics.median(counts)
            low = quantile(counts, 0.25)
            high = quantile(counts, 0.75)
            iqr = high - low
            for sample, count in zip(comparable, counts):
                if abs(count - middle) >= 2 and (count < low - 1.5 * iqr or count > high + 1.5 * iqr):
                    sample["_flags"].append("abnormal-stroke-count")
        else:
            for sample, count in zip(comparable, counts):
                if count >= ABNORMAL_ABSOLUTE:
                    sample["_flags"].append("abnormal-stroke-count")
        shaped = [sample for sample in comparable if sample.get("_traj")]
        writers = defaultdict(list)
        for sample in shaped:
            writers[sample.get("writer_id")].append(sample["_traj"])
        if len(writers) < OUTLIER_MIN_WRITERS + 1:
            continue
        reps = {writer: median_trajectory(trajs) for writer, trajs in writers.items()}
        distances = {}
        for writer, traj in reps.items():
            others = [other for key, other in reps.items() if key != writer]
            distances[writer] = mean_distance(traj, median_trajectory(others))
        ordered = sorted(distances.values())
        middle = statistics.median(ordered)
        mad = statistics.median([abs(value - middle) for value in ordered])
        limit = middle + max(2.5 * mad, 0.12)
        outliers = {writer for writer, distance in distances.items() if distance > limit}
        for sample in shaped:
            if sample.get("writer_id") in outliers:
                sample["_flags"].append("outlier")


def score_writers(samples: list, writers: dict) -> list:
    kept = [sample for sample in samples if sample.get("_kept")]
    buckets = defaultdict(lambda: {"kept": 0, "flagged": 0, "flags": defaultdict(int)})
    for sample in kept:
        bucket = buckets[sample.get("writer_id")]
        bucket["kept"] += 1
        if sample["_flags"]:
            bucket["flagged"] += 1
            for flag in sample["_flags"]:
                bucket["flags"][flag] += 1
    rows = []
    for writer_id, bucket in buckets.items():
        writer = writers.get(writer_id) or {}
        fraction = bucket["flagged"] / bucket["kept"] if bucket["kept"] else 0
        rows.append({
            "id": writer_id,
            "nickname": writer.get("nickname") or writer_id,
            "label": writer.get("_label") or "No invite",
            "kept": bucket["kept"],
            "flagged": bucket["flagged"],
            "fraction": fraction,
            "flags": dict(bucket["flags"]),
            "drop": bucket["kept"] >= DROP_MIN_KEPT and fraction >= DROP_FRACTION,
        })
    rows.sort(key=lambda row: (-row["fraction"], -row["flagged"], str(row["nickname"])))
    return rows


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def thumbnail(sample: dict) -> str:
    strokes = parse_strokes(sample)
    width, height = canvas_of(sample, strokes)
    if _num(sample.get("canvas_w")) < 2 or _num(sample.get("canvas_h")) < 2:
        width, height = 300.0, 300.0
    parts = []
    for stroke in strokes:
        if len(stroke) == 1:
            parts.append(f'<circle cx="{stroke[0][0]:.2f}" cy="{stroke[0][1]:.2f}" r="2.2" fill="#fff"/>')
            continue
        commands = " ".join(
            f'{"M" if index == 0 else "L"}{point[0]:.2f} {point[1]:.2f}' for index, point in enumerate(stroke)
        )
        parts.append(
            f'<path d="{commands}" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<svg viewBox="0 0 {width:.2f} {height:.2f}" width="180" height="180" role="img" aria-label="Sample">'
        f'<rect width="100%" height="100%" fill="#1a1a2e"/>{"".join(parts)}</svg>'
    )


def safe_name(prompt_id: str, used: set) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(prompt_id or "prompt")).strip("-") or "prompt"
    name = cleaned
    suffix = 2
    while name in used:
        name = f"{cleaned}-{suffix}"
        suffix += 1
    used.add(name)
    return name


PAGE_CSS = """
body { margin: 0; background: #f3ecdf; color: #1d1a16; font: 16px/1.45 Georgia, "Noto Serif Thai", serif; }
main { width: min(1100px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 64px; }
a { color: #9f1d22; }
h1 { font-size: 1.8rem; margin: 0 0 8px; }
h2 { margin: 28px 0 12px; font-size: 1.25rem; }
table { border-collapse: collapse; width: 100%; background: #fffdf8; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e4dac8; vertical-align: top; }
.drop { background: #fff1ee; }
.grid { display: flex; flex-wrap: wrap; gap: 12px; }
article { width: 200px; background: #fffdf8; border: 1px solid #e4dac8; border-radius: 12px; padding: 8px; }
article.flagged { border: 3px solid #9f1d22; }
article.older { opacity: 0.55; }
article svg { display: block; width: 180px; height: 180px; border-radius: 8px; background: #1a1a2e; }
.meta { font-size: 0.85rem; margin: 6px 0 0; }
.flags { color: #9f1d22; font-weight: 600; }
.note { color: #6f665c; }
"""


def prompt_page(prompt_id: str, prompt_text: str, samples: list, filename: str) -> str:
    groups = defaultdict(list)
    for sample in samples:
        groups[sample.get("_label") or "No invite"].append(sample)
    names = sorted(groups, key=lambda name: (name == "No invite", name.lower()))
    sections = []
    for name in names:
        cards = []
        ordered = sorted(groups[name], key=lambda sample: (
            str(sample.get("_nickname") or ""),
            sample.get("_rep") or 0,
            sample.get("created_at") or "",
        ))
        for sample in ordered:
            classes = ["sample"]
            if sample["_flags"]:
                classes.append("flagged")
            if not sample.get("_kept"):
                classes.append("older")
            flag_text = ", ".join(sample["_flags"]) if sample["_flags"] else "ok"
            older = "" if sample.get("_kept") else " · older"
            cards.append(
                f'<article class="{" ".join(classes)}" data-sample-id="{esc(sample.get("id"))}">'
                f'{thumbnail(sample)}'
                f'<p class="meta">{esc(sample.get("_nickname") or "writer")} · rep {sample.get("_rep")}'
                f' · {esc(sample.get("_label"))}{older}</p>'
                f'<p class="meta flags">{esc(flag_text)}</p></article>'
            )
        sections.append(f'<section class="invite-group"><h2>{esc(name)}</h2><div class="grid">{"".join(cards)}</div></section>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{esc(prompt_text or prompt_id)}</title>
<style>{PAGE_CSS}</style></head><body><main>
<p><a href="../index.html">All prompts</a></p>
<h1 lang="th">{esc(prompt_text or prompt_id)}</h1>
<p class="note">{esc(prompt_id)} · {len(samples)} samples · flagged ones have a red border · older rewrites are dimmed</p>
{"".join(sections)}
</main></body></html>
"""


def index_page(writer_rows: list, prompts: list, exported: str) -> str:
    drop = [row for row in writer_rows if row["drop"]]
    drop_rows = "".join(
        f'<tr class="drop"><td>{esc(row["nickname"])}</td><td>{esc(row["label"])}</td>'
        f'<td>{row["flagged"]}/{row["kept"]}</td><td>{row["fraction"]:.0%}</td>'
        f'<td>{esc(", ".join(f"{name} {count}" for name, count in sorted(row["flags"].items())))}</td></tr>'
        for row in drop
    ) or '<tr><td colspan="5">None. No writer with at least 3 kept samples is flagged on half or more of them.</td></tr>'
    all_rows = "".join(
        f'<tr class="{"drop" if row["drop"] else ""}"><td>{esc(row["nickname"])}</td><td>{esc(row["label"])}</td>'
        f'<td>{row["flagged"]}/{row["kept"]}</td><td>{row["fraction"]:.0%}</td><td>{"drop" if row["drop"] else ""}</td></tr>'
        for row in writer_rows
    ) or '<tr><td colspan="5">No samples.</td></tr>'
    links = "".join(
        f'<li><a href="prompts/{esc(item["file"])}">{esc(item["text"])}</a> '
        f'<span class="note">{item["flagged"]} flagged / {item["count"]} samples</span></li>'
        for item in prompts
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Write Echo review</title>
<style>{PAGE_CSS}</style></head><body><main>
<h1>Write Echo review</h1>
<p class="note">Export {esc(exported)}. Newest sample per writer, prompt, and repetition. Grouped by invite label.</p>
<h2>Writers to drop</h2>
<table><thead><tr><th>Nickname</th><th>Invite</th><th>Flagged</th><th>Share</th><th>Flags</th></tr></thead>
<tbody>{drop_rows}</tbody></table>
<h2>All writers</h2>
<table><thead><tr><th>Nickname</th><th>Invite</th><th>Flagged</th><th>Share</th><th></th></tr></thead>
<tbody>{all_rows}</tbody></table>
<h2>Prompts</h2>
<ul>{links}</ul>
<p class="note">Near-empty: under {NEAR_EMPTY_POINTS} points or a very short path. Scribble/overfill: path longer than {SCRIBBLE_PATH_DIAGONALS} diagonals, or many strokes across the box. Too fast: under {TOO_FAST_MS} ms or faster than {TOO_FAST_PX_PER_MS} px/ms. Too slow: over {TOO_SLOW_MS // 1000} seconds. Abnormal stroke count: far from the other samples of that prompt. Outlier: resampled shape far from the other writers on that prompt.</p>
</main></body></html>
"""


def analyze(data: dict) -> dict:
    invites = invite_labels(data.get("invites") or [])
    writers = {}
    for writer in data.get("writers") or []:
        if not isinstance(writer, dict) or not writer.get("id"):
            continue
        writer = dict(writer)
        writer["_label"] = label_for(writer, invites)
        writers[writer["id"]] = writer
    samples = prepare(data.get("samples") or [])
    for sample in samples:
        writer = writers.get(sample.get("writer_id")) or {}
        sample["_nickname"] = writer.get("nickname") or sample.get("writer_id") or "writer"
        sample["_label"] = writer.get("_label") or "No invite"
        sample["_flags"] = absolute_flags(sample)
        sample["_strokes_n"] = sample.get("_strokes_n") or len(parse_strokes(sample))
    add_relative_flags(samples)
    return {
        "writers": writers,
        "samples": samples,
        "scores": score_writers(samples, writers),
    }


def write_report(data: dict, out_dir: Path, exported: str) -> None:
    report = analyze(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir = out_dir / "prompts"
    prompt_dir.mkdir(exist_ok=True)
    by_prompt = defaultdict(list)
    texts = {}
    for sample in report["samples"]:
        by_prompt[sample.get("prompt_id")].append(sample)
        if sample.get("prompt_text"):
            texts[sample.get("prompt_id")] = sample.get("prompt_text")
    used = set()
    prompt_links = []
    for prompt_id in sorted(by_prompt, key=lambda key: (texts.get(key) or "", str(key))):
        filename = safe_name(prompt_id, used) + ".html"
        samples = by_prompt[prompt_id]
        (prompt_dir / filename).write_text(
            prompt_page(str(prompt_id), texts.get(prompt_id) or str(prompt_id), samples, filename),
            encoding="utf-8",
        )
        prompt_links.append({
            "file": filename,
            "text": texts.get(prompt_id) or str(prompt_id),
            "count": len(samples),
            "flagged": sum(1 for sample in samples if sample["_flags"]),
        })
    (out_dir / "index.html").write_text(index_page(report["scores"], prompt_links, exported), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review a Write Echo admin JSON export.")
    parser.add_argument("export", nargs="?", help="Path to the admin JSON export")
    parser.add_argument("-o", "--out", default="review", help="Directory for the HTML pages")
    parser.add_argument("--self-test", action="store_true", help="Run the built-in checks and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.export:
        parser.error("an export file is required")
    path = Path(args.export)
    data = load_export(path)
    write_report(data, Path(args.out), path.name)
    print(f"wrote {args.out}")
    return 0


def _line(x0, y0, x1, y1, duration, n=12):
    stroke = []
    for i in range(n):
        mix = i / (n - 1)
        stroke.append({
            "x": x0 + (x1 - x0) * mix,
            "y": y0 + (y1 - y0) * mix,
            "t": int(duration * mix),
            "pressure": 0.5,
        })
    return [stroke]


def _sample(sid, writer, prompt, text, strokes, created, rep=1):
    return {
        "id": sid,
        "writer_id": writer,
        "prompt_id": prompt,
        "prompt_text": text,
        "style": "everyday",
        "strokes": strokes,
        "canvas_w": 300,
        "canvas_h": 300,
        "rep": rep,
        "created_at": created,
        "skipped": False,
    }


def self_test() -> int:
    import tempfile

    writers = [
        {"id": "w-b", "nickname": "Mint", "invite_code": "aaaabbbb"},
        {"id": "w-c", "nickname": "Lek", "invite_code": "ccccdddd"},
        {"id": "w-fast", "nickname": "Fast", "invite_code": "ccccdddd"},
        {"id": "w-slow", "nickname": "Slow", "invite_code": "ccccdddd"},
        {"id": "w-many", "nickname": "Many", "invite_code": "ccccdddd"},
        {"id": "w-drop", "nickname": "Dropme", "invite_code": "aaaabbbb"},
        {"id": "w-empty", "nickname": "Empty", "invite_code": "aaaabbbb"},
        {"id": "w-out", "nickname": "Odd", "invite_code": "ccccdddd"},
    ]
    for index in range(6):
        writers.append({"id": f"w-n{index}", "nickname": f"Norm{index}", "invite_code": "aaaabbbb"})
    invites = [
        {"code": "aaaabbbb", "label": "Bangkok", "created_at": "2026-10-28T00:00:00Z"},
        {"code": "ccccdddd", "label": "Chiang Mai", "created_at": "2026-10-28T00:00:01Z"},
    ]
    normal = _line(30, 40, 220, 200, 900)
    opposite = _line(30, 200, 220, 40, 900)
    samples = []
    for index in range(6):
        samples.append(_sample(f"n{index}", f"w-n{index}", "consonant-0e01", "ก", normal, f"2026-10-28T01:00:0{index}Z"))
    samples.append(_sample("old", "w-b", "consonant-0e01", "ก", [[{"x": 8, "y": 8, "t": 0}]], "2026-10-28T01:00:00Z", 1))
    samples.append(_sample("new", "w-b", "consonant-0e01", "ก", normal, "2026-10-28T02:00:00Z", 1))
    samples.append(_sample("odd", "w-out", "consonant-0e01", "ก", opposite, "2026-10-28T01:00:08Z"))
    samples.append(_sample("empty", "w-empty", "consonant-0e01", "ก", [[{"x": 12, "y": 12, "t": 0}]], "2026-10-28T01:00:09Z"))
    fast = _line(20, 20, 250, 240, 40)
    samples.append(_sample("fast", "w-fast", "word-01", "กิน", fast, "2026-10-28T03:00:00Z"))
    slow = _line(20, 20, 220, 200, 40000)
    samples.append(_sample("slow", "w-slow", "word-02", "ไป", slow, "2026-10-28T03:00:01Z"))
    many = []
    for stroke_index in range(22):
        origin = 20 + stroke_index * 8
        many.append([
            {"x": origin, "y": 40, "t": stroke_index * 200, "pressure": 0.4},
            {"x": origin + 24, "y": 70, "t": stroke_index * 200 + 80, "pressure": 0.4},
        ])
    samples.append(_sample("many", "w-many", "word-03", "มา", many, "2026-10-28T03:00:02Z"))
    scribble = []
    clock = 0
    for stroke_index in range(18):
        stroke = []
        for point_index in range(24):
            stroke.append({
                "x": (point_index * 41 + stroke_index * 17) % 280 + 8,
                "y": (point_index * 23 + stroke_index * 31) % 280 + 8,
                "t": clock,
                "pressure": 0.4,
            })
            clock += 30
        scribble.append(stroke)
    for rep in (1, 2, 3):
        samples.append(_sample(f"scr{rep}", "w-drop", "word-04", "ดี", scribble, f"2026-10-28T04:00:0{rep}Z", rep))
    data = {"exported_at": "2026-10-28T05:00:00Z", "writers": writers, "samples": samples, "invites": invites}
    report = analyze(data)
    by_id = {sample["id"]: sample for sample in report["samples"]}
    problems = []
    if by_id["old"]["_kept"]:
        problems.append("older rewrite was kept")
    if not by_id["new"]["_kept"]:
        problems.append("newer rewrite was dropped")
    if "near-empty" not in by_id["empty"]["_flags"]:
        problems.append(f"empty flags {by_id['empty']['_flags']}")
    if "too-fast" not in by_id["fast"]["_flags"]:
        problems.append(f"fast flags {by_id['fast']['_flags']}")
    if "too-slow" not in by_id["slow"]["_flags"]:
        problems.append(f"slow flags {by_id['slow']['_flags']}")
    if "abnormal-stroke-count" not in by_id["many"]["_flags"]:
        problems.append(f"stroke flags {by_id['many']['_flags']}")
    if "scribble-overfill" not in by_id["scr1"]["_flags"]:
        problems.append(f"scribble flags {by_id['scr1']['_flags']}")
    if "outlier" not in by_id["odd"]["_flags"]:
        problems.append(f"outlier flags {by_id['odd']['_flags']}")
    if any("outlier" in by_id[f"n{index}"]["_flags"] for index in range(6)):
        problems.append("a normal sample was marked outlier")
    dropped = [row["id"] for row in report["scores"] if row["drop"]]
    if dropped != ["w-drop"]:
        problems.append(f"drop list {dropped}")
    if by_id["new"]["_label"] != "Bangkok" or by_id["odd"]["_label"] != "Chiang Mai":
        problems.append("invite labels were not joined")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        write_report(data, out, "self-test.json")
        page = (out / "prompts" / "consonant-0e01.html").read_text(encoding="utf-8")
        index = (out / "index.html").read_text(encoding="utf-8")
        if "<h2>Bangkok</h2>" not in page or "<h2>Chiang Mai</h2>" not in page:
            problems.append("prompt page is not grouped by invite label")
        if "data-sample-id=\"old\"" not in page or "older" not in page:
            problems.append("older sample missing from the prompt page")
        if "Dropme" not in index or "Writers to drop" not in index:
            problems.append("index missing the drop list")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("review self-test ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
