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

PLAIN_VALUE = r"(?:\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?[а-я]?(?![а-я\d])|[а-я](?![а-я.])(?!\s+также))"
VALUE = rf'(?:"{PLAIN_VALUE}"|{PLAIN_VALUE})'
VALUES_RE = re.compile(rf"^\s*[:№]?\s*(?P<values>{VALUE}(?:\s*(?:,|;|\bи\b|\bили\b)\s*{VALUE})*)")
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


def extract_requisites(text: str, offset: int = 0) -> list[Requisite]:
    result: list[Requisite] = []
    for kind, start, end in find_markers(text):
        match = VALUES_RE.match(text[end : end + 100])
        if not match:
            continue
        values = []
        for value in SPLIT_RE.split(match.group("values")):
            if not VALUE_RE.fullmatch(value):
                continue
            value = value.strip('"')
            # буква не может быть номером статьи
            if kind == "article" and value.isalpha():
                continue
            values.append(value)
        if values:
            result.append(Requisite(kind, tuple(values), offset + start, offset + end + match.end()))
    return result
