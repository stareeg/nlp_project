from __future__ import annotations

import re

from .models import Requisite


# у сокращения либо точка ("пп.л"), либо дальше не буква ("пп 1", но не "ппр")
ARTICLE = r"(?:стат(?:ьями|ьям|ьях|ьей|ья|ьи|ье|ью|ей)(?![а-я])|ст(?:\.|(?![а-я])))"
PART = r"(?:част(?:ями|ях|ей|ям|ью|и|ь)(?![а-я])|ч(?:\.|(?![а-я])))"
POINT = r"(?:пунк?т(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])|п(?:\.|(?![а-я])))"
SUBPOINT = (
    r"(?:подпунк?т(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])"
    r"|подп(?:\.|(?![а-я]))|пп(?:\.|(?![а-я]))|п\s*/\s*п)"
)
MARKER_RE = re.compile(
    rf"(?<![а-яa-z])(?:(?P<subpoint>{SUBPOINT})|(?P<article>{ARTICLE})|(?P<part>{PART})|(?P<point>{POINT}))"
)

NUMBER = r"\d+(?:\.\d+)*"
# диапазон: "10-12", "10 - 12", "10 – 12" (тире уже заменено на дефис), "с 10 по 12"
RANGE_SEP = r"(?:\s*-\s*|\s+по\s+)"
RANGE_SEP_RE = re.compile(RANGE_SEP)
# порядковые числительные: "части первой статьи 5", "ч. вторая ст. 7"
ORDINAL_STEMS = {
    "перв": "1", "втор": "2", "трет": "3", "четверт": "4", "пят": "5", "шест": "6", "седьм": "7",
    "восьм": "8", "девят": "9", "десят": "10", "одиннадцат": "11", "двенадцат": "12",
    "тринадцат": "13", "четырнадцат": "14", "пятнадцат": "15", "шестнадцат": "16",
    "семнадцат": "17", "восемнадцат": "18", "девятнадцат": "19", "двадцат": "20",
}
ORDINAL_ENDINGS = (
    "ого", "ому", "ыми", "ый", "ой", "ая", "ое", "ые", "ом", "ую", "ым", "ых",
    "ий", "ья", "ье", "ьего", "ьему", "ьем", "ью", "ьей", "ьим", "ьих", "ьи",
)
ORDINAL_STEM = "|".join(sorted(ORDINAL_STEMS, key=len, reverse=True))
ORDINAL_ENDING = "|".join(sorted(ORDINAL_ENDINGS, key=len, reverse=True))
ORDINAL = rf"(?:{ORDINAL_STEM})(?:{ORDINAL_ENDING})(?![а-я])"
ORDINAL_RE = re.compile(rf"(?P<stem>{ORDINAL_STEM})(?:{ORDINAL_ENDING})")
PLAIN_VALUE = (
    rf"(?:{NUMBER}(?:{RANGE_SEP}{NUMBER})?[а-я]?(?![а-я\d])"
    rf"|{ORDINAL}"
    r"|[а-я](?![а-я.])(?!\s+также))"
)
VALUE = rf'(?:"{PLAIN_VALUE}"|{PLAIN_VALUE})'
VALUES_RE = re.compile(
    rf"^\s*[:№]?\s*(?:с\s+(?={NUMBER}\s+по\s+\d))?(?P<values>{VALUE}(?:\s*(?:,|;|\bи\b|\bили\b)\s*{VALUE})*)"
)
VALUE_RE = re.compile(rf"^{VALUE}$")
SPLIT_RE = re.compile(r"\s*(?:,|;|\bи\b|\bили\b)\s*")

# правильные формы слов, от них строим опечатки на одну букву
WORD_FORMS = {
    "article": ["стать" + e for e in ("я", "и", "е", "ю", "ей", "ям", "ями", "ях")] + ["статей"],
    "part": ["част" + e for e in ("ь", "и", "ью", "ей", "ям", "ями", "ях")],
    "point": ["пункт" + e for e in ("", "а", "е", "у", "ом", "ы", "ов", "ам", "ами", "ах")],
    "subpoint": ["подпункт" + e for e in ("", "а", "е", "у", "ом", "ы", "ов", "ам", "ами", "ах")],
}
ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
# обычные слова, которые отличаются от маркера на одну букву
NOT_TYPOS = {"честь", "чести", "честью", "статуя", "статуи", "статую", "счасть"}
WORD_RE = re.compile(r"(?<![а-яa-z])[а-я]{5,12}(?![а-яa-z])")


def one_edit(word: str) -> set[str]:
    result: set[str] = set()
    for i in range(len(word) + 1):
        for char in ALPHABET:
            result.add(word[:i] + char + word[i:])
        if i < len(word):
            result.add(word[:i] + word[i + 1 :])
            for char in ALPHABET:
                result.add(word[:i] + char + word[i + 1 :])
        if i < len(word) - 1:
            result.add(word[:i] + word[i + 1] + word[i] + word[i + 2 :])
    return result


def build_typos() -> dict[str, str]:
    forms = {form: kind for kind, words in WORD_FORMS.items() for form in words}
    typos: dict[str, str] = {}
    conflicts: set[str] = set()
    for form, kind in forms.items():
        for typo in one_edit(form):
            if len(typo) < 5 or typo in forms or typo in NOT_TYPOS:
                continue
            if typos.get(typo, kind) != kind:
                conflicts.add(typo)
            typos[typo] = kind
    return {typo: kind for typo, kind in typos.items() if typo not in conflicts}


TYPOS = build_typos()


def find_markers(text: str) -> list[tuple[str, int, int]]:
    markers = [(m.lastgroup, m.start(), m.end()) for m in MARKER_RE.finditer(text)]
    spans = [(start, end) for _, start, end in markers]
    for m in WORD_RE.finditer(text):
        kind = TYPOS.get(m.group(0))
        if kind and not any(start < m.end() and m.start() < end for start, end in spans):
            markers.append((kind, m.start(), m.end()))
    return sorted(markers, key=lambda marker: marker[1])


def number_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def normalize_value(value: str) -> tuple[str, bool] | None:
    """Приводит значение к строке; второй элемент - было ли оно записано словом ("первой")."""
    m = ORDINAL_RE.fullmatch(value)
    if m:
        return ORDINAL_STEMS[m["stem"]], True
    if not RANGE_SEP_RE.search(value) or re.fullmatch(r"\d+(?:\.\d+)*-\d+(?:\.\d+)*[а-я]?", value):
        return value, False
    # "10 - 12", "10 по 12": склеиваем в "10-12", если это похоже на диапазон (правая граница больше),
    # иначе ("ст. 158 - 3 года") оставляем только левое число
    left, right = RANGE_SEP_RE.split(value, maxsplit=1)
    suffix = right[-1] if right[-1].isalpha() else ""
    right = right.rstrip("абвгдежзийклмнопрстуфхцчшщъыьэюя")
    if number_key(right) > number_key(left):
        return f"{left}-{right}{suffix}", False
    return left, False


# что может стоять сразу после реквизита, записанного словом: "части первой статьи 5"
HIGHER = {"subpoint": {"point", "part", "article"}, "point": {"part", "article"}, "part": {"article"}}


def extract_requisites(text: str, offset: int = 0) -> list[Requisite]:
    found: list[tuple[Requisite, bool]] = []
    for kind, start, end in find_markers(text):
        match = VALUES_RE.match(text[end : end + 100])
        if not match:
            continue
        values = []
        ordinal = False
        for value in SPLIT_RE.split(match.group("values")):
            if not VALUE_RE.fullmatch(value):
                continue
            normalized = normalize_value(value.strip('"'))
            if normalized is None:
                continue
            value, is_ordinal = normalized
            # буква не может быть номером статьи; статьи словами ("статья первая") не пишут
            if kind == "article" and (value.isalpha() or is_ordinal):
                continue
            ordinal = ordinal or is_ordinal
            if value not in values:
                values.append(value)
        if values:
            found.append((Requisite(kind, tuple(values), offset + start, offset + end + match.end()), ordinal))

    result: list[Requisite] = []
    for i, (req, ordinal) in enumerate(found):
        if ordinal:
            # "часть первая" без статьи следом - это часть кодекса ("ст. 217 части второй НК РФ"),
            # а не часть статьи, поэтому берём такой реквизит только перед статьёй/частью
            nxt = found[i + 1][0] if i + 1 < len(found) else None
            between = text[req.end - offset : nxt.start - offset] if nxt else ""
            if nxt is None or nxt.kind not in HIGHER.get(req.kind, ()) or not re.fullmatch(r"[\s,]*", between):
                continue
        result.append(req)
    return result
