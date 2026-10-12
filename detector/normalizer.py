from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

from .models import Token


_DASHES = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
})
_QUOTES = str.maketrans({
    "«": '"',
    "»": '"',
    "„": '"',
    "“": '"',
    "”": '"',
    "‟": '"',
    "‘": "'",
    "’": "'",
})
_HOMOGLYPHS = str.maketrans("aceopxykmtbh", "асеорхукмтвн")
_MIXED_WORD_RE = re.compile(r"[a-zа-я]*(?:[a-z][а-я]|[а-я][a-z])[a-zа-я]*")
_SPACE_RE = re.compile(r"[\s\u00a0\u2007\u202f]+")
_NUMBER_SIGN_RE = re.compile(r"(?i)(?<![\wа-яё])(?:no|n)\.?\s*(?=\d)")
_NUMBER_SPACE_RE = re.compile(r"№\s+(?=\d)")

# Punctuation is deliberately omitted. This makes an alias robust to optional
# commas, quotes and dots while word boundaries remain explicit.
_TOKEN_RE = re.compile(
    r"№\d+(?:[./-]\d+)*(?:-[a-zа-я]+)?"
    r"|\d+(?:[./-]\d+)*(?:-[a-zа-я]+)?"
    r"|[a-zа-я]+(?:-[a-zа-я0-9]+)*",
    re.IGNORECASE,
)
_RUSSIAN_WORD_RE = re.compile(r"^[а-я]+$")
_VOWELS = "аеиоуыэюя"


def _remove_suffix(value: str, suffixes: tuple[str, ...]) -> tuple[str, bool]:
    for suffix in suffixes:
        if value.endswith(suffix):
            return value[: -len(suffix)], True
    return value, False


def _russian_stem(word: str) -> str:
    """Small dependency-free implementation of the Russian Porter stemmer."""
    if len(word) < 4 or not _RUSSIAN_WORD_RE.fullmatch(word):
        return word
    rv_index = next((index + 1 for index, char in enumerate(word) if char in _VOWELS), len(word))
    prefix, rv = word[:rv_index], word[rv_index:]

    rv, removed = _remove_suffix(rv, ("ившись", "ывшись", "ивши", "ывши", "ив", "ыв"))
    if not removed:
        for suffix in ("вшись", "вши", "в"):
            if rv.endswith(suffix) and len(rv) > len(suffix) and rv[-len(suffix) - 1] in "ая":
                rv = rv[: -len(suffix)]
                removed = True
                break
    if not removed:
        rv, _ = _remove_suffix(rv, ("ся", "сь"))
        rv, adjective = _remove_suffix(
            rv,
            (
                "ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое",
                "ей", "ий", "ый", "ой", "ем", "им", "ым", "ом", "их", "ых",
                "ую", "юю", "ая", "яя", "ою", "ею",
            ),
        )
        if adjective:
            rv, participle = _remove_suffix(rv, ("ивш", "ывш", "ующ"))
            if not participle:
                for suffix in ("ем", "нн", "вш", "ющ", "щ"):
                    if rv.endswith(suffix) and len(rv) > len(suffix) and rv[-len(suffix) - 1] in "ая":
                        rv = rv[: -len(suffix)]
                        break
        else:
            rv, verb = _remove_suffix(
                rv,
                (
                    "ила", "ыла", "ена", "ейте", "уйте", "ите", "или", "ыли", "ей",
                    "уй", "ил", "ыл", "им", "ым", "ен", "ило", "ыло", "ено", "ят",
                    "ует", "уют", "ит", "ыт", "ены", "ить", "ыть", "ишь", "ую", "ю",
                ),
            )
            if not verb:
                for suffix in ("ла", "на", "ете", "йте", "ли", "й", "л", "ем", "н", "ло", "но", "ет", "ны", "ть", "ешь", "нно"):
                    if rv.endswith(suffix) and len(rv) > len(suffix) and rv[-len(suffix) - 1] in "ая":
                        rv = rv[: -len(suffix)]
                        verb = True
                        break
            if not verb:
                rv, _ = _remove_suffix(
                    rv,
                    (
                        "иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов",
                        "ие", "ье", "еи", "ии", "ей", "ой", "ий", "ям", "ем", "ам",
                        "ом", "ах", "ях", "ию", "ью", "ия", "ья", "евы", "овы", "ы",
                        "ь", "й", "у", "ю", "я", "а", "ев", "ов", "е", "и", "о",
                    ),
                )

    rv, _ = _remove_suffix(rv, ("и",))
    stemmed = prefix + rv
    if stemmed.endswith("ость") or stemmed.endswith("ост"):
        stemmed = re.sub(r"ост(?:ь)?$", "", stemmed)
    if stemmed.endswith("ейше"):
        stemmed = stemmed[:-4]
    if stemmed.endswith("нн"):
        stemmed = stemmed[:-1]
    stemmed = re.sub(r"ь$", "", stemmed)
    return stemmed or word


@lru_cache(maxsize=None)
def _canonical_token(value: str) -> str:
    if "-" in value and not value[0].isdigit():
        return "-".join(_russian_stem(part) for part in value.split("-"))
    return _russian_stem(value)


def normalize_text(text: str) -> str:
    """Return a conservative searchable form of Russian legal text."""
    value = unicodedata.normalize("NFKC", text)
    value = value.translate(_DASHES).translate(_QUOTES)
    value = value.casefold().replace("ё", "е")
    # Latin look-alikes inside Cyrillic words, e.g. "CК РФ" typed with Latin C.
    value = _MIXED_WORD_RE.sub(lambda match: match.group(0).translate(_HOMOGLYPHS), value)
    value = _NUMBER_SIGN_RE.sub("№", value)
    value = _NUMBER_SPACE_RE.sub("№", value)
    return _SPACE_RE.sub(" ", value).strip()


def tokenize(text: str) -> list[Token]:
    return [Token(_canonical_token(m.group(0)), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def alias_tokens(alias: str) -> tuple[str, ...]:
    normalized = normalize_text(alias)
    return tuple(token.value for token in tokenize(normalized))
