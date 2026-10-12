from __future__ import annotations

import re

from .models import Requisite


# An abbreviation is either closed by a dot ("пп.л") or must not be the
# beginning of a longer word ("пп 1" but not "ппр").
_ARTICLE = r"(?:стат(?:ьями|ьям|ьях|ьей|ья|ьи|ье|ью|ей)(?![а-я])|ст(?:\.|(?![а-я])))"
_POINT = (
    r"(?:пункт(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])"
    r"|пунт(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])"
    r"|п(?:\.|(?![а-я]))"
    r"|част(?:ями|ях|ей|ям|ью|и|ь)(?![а-я])"
    r"|ч(?:\.|(?![а-я])))"
)
_SUBPOINT = (
    r"(?:подпункт(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])"
    r"|подпунт(?:ами|ах|ов|ам|ом|а|е|у|ы)?(?![а-я])"
    r"|подп(?:\.|(?![а-я]))"
    r"|пп(?:\.|(?![а-я]))"
    r"|п\s*/\s*п)"
)
_MARKER_RE = re.compile(
    rf"(?<![а-яa-z])(?:(?P<subpoint>{_SUBPOINT})|(?P<article>{_ARTICLE})|(?P<point>{_POINT}))",
    re.IGNORECASE,
)

_PLAIN_ATOM = r"(?:\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?[а-я]?(?![а-я\d])|[а-я](?![а-я.])(?!\s+также))"
_ATOM = rf'(?:"{_PLAIN_ATOM}"|{_PLAIN_ATOM})'
_VALUE_EXPRESSION_RE = re.compile(
    rf"^\s*[:№]?\s*(?P<values>{_ATOM}(?:\s*(?:,|;|\bи\b|\bили\b)\s*{_ATOM})*)",
    re.IGNORECASE,
)
_ATOM_RE = re.compile(rf"^{_ATOM}$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*(?:,|;|\bи\b|\bили\b)\s*", re.IGNORECASE)

_CANONICAL_FORMS = {
    "article": ("стать", ("я", "и", "е", "ю", "ей", "ям", "ями", "ях"), ("статей",)),
    "point": ("пункт", ("", "а", "е", "у", "ом", "ы", "ов", "ам", "ами", "ах"), ()),
    "part": ("част", ("ь", "и", "ью", "ей", "ям", "ями", "ях"), ()),
    "subpoint": ("подпункт", ("", "а", "е", "у", "ом", "ы", "ов", "ам", "ами", "ах"), ()),
}
_ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
# Real words one edit away from a marker form.
_TYPO_STOPWORDS = {"честь", "чести", "честью", "статуя", "статуи", "статую", "счасть", "пункты"}
_WORD_RE = re.compile(r"(?<![а-яa-z])[а-я]{5,12}(?![а-яa-z])")


def _one_edit_variants(word: str) -> set[str]:
    variants: set[str] = set()
    for index in range(len(word) + 1):
        for char in _ALPHABET:
            variants.add(word[:index] + char + word[index:])
        if index < len(word):
            variants.add(word[:index] + word[index + 1 :])
            for char in _ALPHABET:
                variants.add(word[:index] + char + word[index + 1 :])
        if index < len(word) - 1:
            variants.add(word[:index] + word[index + 1] + word[index] + word[index + 2 :])
    return variants


def _build_typo_markers() -> dict[str, str]:
    forms: dict[str, str] = {}
    for kind, (stem, endings, extra) in _CANONICAL_FORMS.items():
        for form in (*(stem + ending for ending in endings), *extra):
            forms[form] = "point" if kind == "part" else kind
    typos: dict[str, str] = {}
    ambiguous: set[str] = set()
    for form, kind in forms.items():
        for variant in _one_edit_variants(form):
            if len(variant) < 5 or variant in forms or variant in _TYPO_STOPWORDS:
                continue
            if typos.get(variant, kind) != kind:
                ambiguous.add(variant)
            typos[variant] = kind
    return {variant: kind for variant, kind in typos.items() if variant not in ambiguous}


_TYPO_MARKERS = _build_typo_markers()


def _markers(text: str) -> list[tuple[str, int, int]]:
    markers = [
        (
            "subpoint" if match.group("subpoint") else "article" if match.group("article") else "point",
            match.start(),
            match.end(),
        )
        for match in _MARKER_RE.finditer(text)
    ]
    covered = [(start, end) for _, start, end in markers]
    for match in _WORD_RE.finditer(text):
        kind = _TYPO_MARKERS.get(match.group(0).casefold())
        if kind and not any(start < match.end() and match.start() < end for start, end in covered):
            markers.append((kind, match.start(), match.end()))
    return sorted(markers, key=lambda item: item[1])


def extract_requisites(text: str, offset: int = 0) -> list[Requisite]:
    """Extract labelled article/point/subpoint values from a text fragment."""
    result: list[Requisite] = []
    for kind, start, end in _markers(text):
        tail = text[end : end + 100]
        value_match = _VALUE_EXPRESSION_RE.match(tail)
        if not value_match:
            continue
        values = tuple(
            value.strip('"').casefold().replace("ё", "е")
            for value in _SPLIT_RE.split(value_match.group("values"))
            if _ATOM_RE.fullmatch(value) and not (kind == "article" and value.strip('"').isalpha())
        )
        if not values:
            continue
        result.append(
            Requisite(
                kind=kind,
                values=values,
                start=offset + start,
                end=offset + end + value_match.end(),
            )
        )
    return result


def has_requisite_marker(text: str) -> bool:
    return _MARKER_RE.search(text) is not None


__all__ = ["extract_requisites", "has_requisite_marker"]
