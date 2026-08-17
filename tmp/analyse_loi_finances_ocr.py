from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


def lines(path: Path):
    groups = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row.get("level") == "5" and (row.get("text") or "").strip():
                groups[(row["block_num"], row["par_num"], row["line_num"])].append(row)
    segments = []
    for words in groups.values():
        words.sort(key=lambda item: int(item["left"]))
        top = min(int(item["top"]) for item in words)
        bottom = max(int(item["top"]) + int(item["height"]) for item in words)
        left = min(int(item["left"]) for item in words)
        right = max(int(item["left"]) + int(item["width"]) for item in words)
        confidence = sum(float(item["conf"]) for item in words) / len(words)
        text = re.sub(r"\s+", " ", " ".join(item["text"] for item in words)).strip()
        segments.append((top, bottom, left, right, confidence, text))
    segments.sort(key=lambda item: ((item[0] + item[1]) / 2, item[2]))
    merged = []
    for segment in segments:
        center = (segment[0] + segment[1]) / 2
        if merged and abs(center - merged[-1][0]) <= 17:
            merged[-1][1].append(segment)
        else:
            merged.append([center, [segment]])
    result = []
    for _, group in merged:
        group.sort(key=lambda item: item[2])
        text = " ".join(item[5] for item in group)
        conf = sum(item[4] for item in group) / len(group)
        result.append((min(item[0] for item in group), min(item[2] for item in group), conf, text))
    return result


root = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else "all"
page_filter = {int(value) for value in sys.argv[3].split(",")} if len(sys.argv) > 3 else None
for path in sorted(root.glob("page-*.tsv")):
    page = int(re.search(r"(\d+)$", path.stem).group(1))
    if page_filter is not None and page not in page_filter:
        continue
    for top, left, confidence, text in lines(path):
        keep = True
        if mode == "structure":
            keep = bool(re.search(r"^(?:TITRE|CHAPITRE|Section|SECTION|Sous-section|Article)", text, re.I))
        elif mode == "low":
            keep = confidence < 80
        elif mode == "headers":
            keep = top < 350
        elif mode == "weird":
            keep = bool(re.search(r"(?:\bI[!”“]|[0-9][°“”‘])", text))
        if keep:
            print(f"{page:02d} {top:4d} {left:4d} {confidence:6.2f} | {text}")
