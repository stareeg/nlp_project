from __future__ import annotations

import re

from .models import Requisite


_ARTICLE = r"(?:стат(?:ьями|ьям|ьях|ьей|ья|ьи|ье|ью|ей)|ст\.?)(?![а-я])"
_POINT = (
    r"(?:пункт(?:ами|ах|ов|ам|ом|а|е|у|ы)?"
    r"|пунт(?:ами|ах|ов|ам|ом|а|е|у|ы)?"
    r"|п\.?(?![а-я])"
    r"|част(?:ями|ях|ей|ям|ью|и|ь)"
    r"|ч\.?(?![а-я]))"
)
_SUBPOINT = (
    r"(?:подпункт(?:ами|ах|ов|ам|ом|а|е|у|ы)?"
    r"|подпунт(?:ами|ах|ов|ам|ом|а|е|у|ы)?"
    r"|пп\.?(?![а-я])"
    r"|п\s*/\s*п)"
)
_MARKER_RE = re.compile(
    rf"(?<![а-яa-z])(?:(?P<subpoint>{_SUBPOINT})|(?P<article>{_ARTICLE})|(?P<point>{_POINT}))",
    re.IGNORECASE,
)

_ATOM = r"(?:\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?[а-я]?(?![а-я\d])|[а-я](?![а-я.])(?!\s+также))"
_VALUE_EXPRESSION_RE = re.compile(
    rf"^\s*[:№]?\s*(?P<values>{_ATOM}(?:\s*(?:,|;|\bи\b|\bили\b)\s*{_ATOM})*)",
    re.IGNORECASE,
)
_ATOM_RE = re.compile(rf"^{_ATOM}$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*(?:,|;|\bи\b|\bили\b)\s*", re.IGNORECASE)


def extract_requisites(text: str, offset: int = 0) -> list[Requisite]:
    """Extract labelled article/point/subpoint values from a text fragment."""
    result: list[Requisite] = []
    for marker in _MARKER_RE.finditer(text):
        tail = text[marker.end() : marker.end() + 100]
        value_match = _VALUE_EXPRESSION_RE.match(tail)
        if not value_match:
            continue
        kind = "subpoint" if marker.group("subpoint") else "article" if marker.group("article") else "point"
        values = tuple(
            value.casefold().replace("ё", "е")
            for value in _SPLIT_RE.split(value_match.group("values"))
            if _ATOM_RE.fullmatch(value) and not (kind == "article" and value.isalpha())
        )
        if not values:
            continue
        result.append(
            Requisite(
                kind=kind,
                values=values,
                start=offset + marker.start(),
                end=offset + marker.end() + value_match.end(),
            )
        )
    return result


def has_requisite_marker(text: str) -> bool:
    return _MARKER_RE.search(text) is not None


__all__ = ["extract_requisites", "has_requisite_marker"]
