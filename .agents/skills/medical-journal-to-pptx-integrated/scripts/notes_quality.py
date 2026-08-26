#!/usr/bin/env python3
"""Shared speaker-note quality checks for spec, asset, and PPTX QA."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Iterable


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
# Conservative, high-frequency Simplified-only forms. Keep this shared so the
# three QA entry points cannot silently drift apart.
SIMPLIFIED_ONLY_RE = re.compile(
    r"[这为国医门体会发与说经从对过还进开应实术图们来时种样学总临观现无区线数间题处见较让给认写听读简"
    r"个别关风险资华业东书买云产众优传伤伦价仅儿党兰兴农冲决冻净凉减务动劳势协单卫历厉压县双变叶号员"
    r"团园围圆场坏块坚坛执扩扫扬扰抚护报担拟拢拣拥拦拨择挤挥损换据捞检测济浓浅灭灯灵灾点炼热爱爷牵状"
    r"独狭猎玛环现产电疗监盖盘着矫码礼离秃种积稳穷窝竞笔笼节茎茧荐药获营虑虚虫虽蚀蚁补装见观规视"
    r"觉触誉计订认讨让议记讲许论设证评词译试诗诚话详语误询该课调谈谋谱负财责败账贩质贪贫购贯贴贵贷费"
    r"贺资赋赌赏赔赖赚赵赶趋跃车轨转轮软轴轻载轰较输边辽达迁过运还进远违连迟适选递逻遗邮邻酝释里鉴长门"
    r"间闷闯闸闻阁队阳阴阵阶际陆陈险随隐难雾静顶项顺须顾顿颁预领颈频颗题颜额风飞饥饭饮馆驱验惊鱼鸟鸡麦]"
)
EMOJI_RANGES = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF))
TAKEAWAY_MARKERS = ("✅", "💡", "⚠")
NEAR_DUPLICATE_THRESHOLD = 0.97
NEAR_DUPLICATE_MIN_LENGTH = 24
PAGE_ORDINAL_RE = re.compile(
    r"(?:"
    r"第\s*(?:\d+|[〇零一二兩两三四五六七八九十百千]+)\s*"
    r"(?:頁|页|張\s*投影片|张\s*(?:投影片|幻灯片))"
    r"|第\s*(?:\d+|[〇零一二兩两三四五六七八九十百千]+)\s*個\s*"
    r"(?:教學(?:重點|頁面|頁|段落)|投影片)"
    r"|(?:slide|page)\s*(?:no\.?\s*)?[#:]?\s*\d+"
    r")",
    re.IGNORECASE,
)
CLINICAL_NUMERIC_RE = re.compile(
    r"(?:\b(?:hr|or|rr|ci|n)\s*(?:[=:<>]|\b)|hazard\s*ratio|odds\s*ratio|"
    r"risk\s*ratio|confidence\s*interval|p\s*[<=>]|[%％]|樣本數|样本数|"
    r"信賴區間|可信區間)",
    re.IGNORECASE,
)


def has_structural_emoji(text: str) -> bool:
    # A marker is structural only when it appears in the opening scan block;
    # one decorative glyph appended to otherwise unstructured prose is not.
    opening = text.lstrip()[:96]
    return any(
        any(start <= ord(character) <= end for start, end in EMOJI_RANGES)
        for character in opening
    )


def note_diversity_failure(text: str) -> str | None:
    """Reject glyph padding and short repeated phrases masquerading as notes."""
    characters = CJK_RE.findall(text)
    if not characters:
        return None
    unique = len(set(characters))
    dominant = max(characters.count(character) for character in set(characters))
    if unique < 4 or dominant / len(characters) > 0.55:
        return (
            f"speaker notes are repetitive padding ({unique} unique CJK characters; "
            f"dominant-character share {dominant / len(characters):.0%})"
        )

    joined = "".join(characters)
    for period in range(2, min(12, len(joined) // 3) + 1):
        for start in range(0, len(joined) - period * 3 + 1):
            phrase = joined[start:start + period]
            end = start
            while joined[end:end + period] == phrase:
                end += period
            repetitions = (end - start) // period
            if repetitions >= 3 and (end - start) / len(joined) >= 0.60:
                return (
                    "speaker notes contain repeated phrase padding "
                    f"({phrase!r} repeated {repetitions} times)"
                )
    return None


def normalized_note_signature(text: str) -> str:
    """Return a boilerplate signature that ignores page/slide/teaching ordinals.

    Clinical values remain significant so legitimately page-specific data notes
    are not collapsed merely because their surrounding sentence is similar.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = PAGE_ORDINAL_RE.sub("", normalized)
    return "".join(character for character in normalized if character.isalnum())


def _has_clinical_numeric_difference(left: str, right: str) -> bool:
    """Keep genuine statistical values meaningful in near-duplicate analysis."""
    normalized_left = PAGE_ORDINAL_RE.sub(
        "", unicodedata.normalize("NFKC", left).casefold()
    )
    normalized_right = PAGE_ORDINAL_RE.sub(
        "", unicodedata.normalize("NFKC", right).casefold()
    )
    left_numbers = re.findall(r"\d+(?:\.\d+)?", normalized_left)
    right_numbers = re.findall(r"\d+(?:\.\d+)?", normalized_right)
    return (
        left_numbers != right_numbers
        and bool(CLINICAL_NUMERIC_RE.search(normalized_left))
        and bool(CLINICAL_NUMERIC_RE.search(normalized_right))
    )


def duplicate_note_failures(
    entries: Iterable[tuple[int, str]], *, maximum_reuse: int = 2
) -> list[str]:
    materialized = list(entries)
    groups: dict[str, list[int]] = defaultdict(list)
    signatures: list[tuple[int, str, str]] = []
    for index, text in materialized:
        signature = normalized_note_signature(text)
        if signature:
            groups[signature].append(index)
            signatures.append((index, text, signature))
    failures = [
        "Slides " + ", ".join(str(index) for index in indexes)
        + " reuse the same normalized speaker notes; page-specific teaching notes are required."
        for indexes in groups.values()
        if len(indexes) > maximum_reuse
    ]

    parent = list(range(len(signatures)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(signatures)):
        left_index, left_text, left_signature = signatures[left]
        if len(left_signature) < NEAR_DUPLICATE_MIN_LENGTH:
            continue
        for right in range(left):
            right_index, right_text, right_signature = signatures[right]
            if (
                left_signature == right_signature
                or len(right_signature) < NEAR_DUPLICATE_MIN_LENGTH
                or _has_clinical_numeric_difference(left_text, right_text)
            ):
                continue
            similarity = SequenceMatcher(
                None, left_signature, right_signature, autojunk=False
            ).ratio()
            if similarity >= NEAR_DUPLICATE_THRESHOLD:
                union(left, right)

    near_groups: dict[int, list[int]] = defaultdict(list)
    for position, (index, _text, _signature) in enumerate(signatures):
        near_groups[find(position)].append(index)
    failures.extend(
        "Slides " + ", ".join(str(index) for index in indexes)
        + f" reuse near-identical speaker-note boilerplate (at least {NEAR_DUPLICATE_THRESHOLD:.0%} "
        "normalized similarity); substantive page-specific teaching notes are required."
        for indexes in near_groups.values()
        if len(indexes) > maximum_reuse
    )
    return failures


def has_closing_takeaway(text: str) -> bool:
    """Require a takeaway marker in the latter half, not only as decoration up front."""
    last = max((text.rfind(marker) for marker in TAKEAWAY_MARKERS), default=-1)
    return last >= max(1, len(text) // 2)
