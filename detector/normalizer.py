from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

from .models import Token


DASHES = str.maketrans({char: "-" for char in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})
QUOTES = str.maketrans({"«": '"', "»": '"', "„": '"', "“": '"', "”": '"', "‟": '"', "‘": "'", "’": "'"})
# латинские буквы, похожие на русские ("CК РФ" в словаре набрано с латинской C)
HOMOGLYPHS = str.maketrans("aceopxykmtbh", "асеорхукмтвн")
MIXED_WORD_RE = re.compile(r"[a-zа-я]*(?:[a-z][а-я]|[а-я][a-z])[a-zа-я]*")
SPACE_RE = re.compile(r"[\s\u00a0\u2007\u202f]+")
NUMBER_SIGN_RE = re.compile(r"(?<![\wа-я])(?:no|n)\.?\s*(?=\d)")
NUMBER_SPACE_RE = re.compile(r"№\s+(?=\d)")
# знаки препинания не токены, поэтому запятые и кавычки в названии не мешают
TOKEN_RE = re.compile(r"№\d+(?:[./-]\d+)*(?:-[a-zа-я]+)?|\d+(?:[./-]\d+)*(?:-[a-zа-я]+)?|[a-zа-я]+(?:-[a-zа-я0-9]+)*")
RUSSIAN_WORD_RE = re.compile(r"^[а-я]+$")
VOWELS = "аеиоуыэюя"

GERUND = ("ившись", "ывшись", "ивши", "ывши", "ив", "ыв")
GERUND_AFTER_A = ("вшись", "вши", "в")
ADJECTIVE = (
    "ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое", "ей", "ий", "ый", "ой",
    "ем", "им", "ым", "ом", "их", "ых", "ую", "юю", "ая", "яя", "ою", "ею",
)
PARTICIPLE = ("ивш", "ывш", "ующ")
PARTICIPLE_AFTER_A = ("ем", "нн", "вш", "ющ", "щ")
VERB = (
    "ила", "ыла", "ена", "ейте", "уйте", "ите", "или", "ыли", "ей", "уй", "ил", "ыл", "им", "ым",
    "ен", "ило", "ыло", "ено", "ят", "ует", "уют", "ит", "ыт", "ены", "ить", "ыть", "ишь", "ую", "ю",
)
VERB_AFTER_A = ("ла", "на", "ете", "йте", "ли", "й", "л", "ем", "н", "ло", "но", "ет", "ны", "ть", "ешь", "нно")
NOUN = (
    "иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов", "ие", "ье", "еи", "ии", "ей", "ой",
    "ий", "ям", "ем", "ам", "ом", "ах", "ях", "ию", "ью", "ия", "ья", "евы", "овы", "ы", "ь", "й",
    "у", "ю", "я", "а", "ев", "ов", "е", "и", "о",
)


def cut(word: str, endings: tuple[str, ...]) -> tuple[str, bool]:
    for ending in endings:
        if word.endswith(ending):
            return word[: -len(ending)], True
    return word, False


def cut_after_a(word: str, endings: tuple[str, ...]) -> tuple[str, bool]:
    for ending in endings:
        if word.endswith(ending) and len(word) > len(ending) and word[-len(ending) - 1] in "ая":
            return word[: -len(ending)], True
    return word, False


def russian_stem(word: str) -> str:
    # упрощённый стеммер Портера, чтобы "Гражданского кодекса" совпадало с "Гражданский кодекс"
    if len(word) < 4 or not RUSSIAN_WORD_RE.fullmatch(word):
        return word
    split = next((i + 1 for i, char in enumerate(word) if char in VOWELS), len(word))
    prefix, rv = word[:split], word[split:]

    rv, done = cut(rv, GERUND)
    if not done:
        rv, done = cut_after_a(rv, GERUND_AFTER_A)
    if not done:
        rv, _ = cut(rv, ("ся", "сь"))
        rv, adjective = cut(rv, ADJECTIVE)
        if adjective:
            rv, participle = cut(rv, PARTICIPLE)
            if not participle:
                rv, _ = cut_after_a(rv, PARTICIPLE_AFTER_A)
        else:
            rv, verb = cut(rv, VERB)
            if not verb:
                rv, verb = cut_after_a(rv, VERB_AFTER_A)
            if not verb:
                rv, _ = cut(rv, NOUN)

    rv, _ = cut(rv, ("и",))
    stem = prefix + rv
    stem = re.sub(r"ость?$", "", stem)
    if stem.endswith("ейше"):
        stem = stem[:-4]
    if stem.endswith("нн"):
        stem = stem[:-1]
    stem = re.sub(r"ь$", "", stem)
    return stem or word


@lru_cache(maxsize=None)
def stem_token(value: str) -> str:
    if "-" in value and not value[0].isdigit():
        return "-".join(russian_stem(part) for part in value.split("-"))
    return russian_stem(value)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(DASHES).translate(QUOTES)
    text = text.casefold().replace("ё", "е")
    text = MIXED_WORD_RE.sub(lambda m: m.group(0).translate(HOMOGLYPHS), text)
    text = NUMBER_SIGN_RE.sub("№", text)
    text = NUMBER_SPACE_RE.sub("№", text)
    return SPACE_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[Token]:
    return [Token(stem_token(m.group(0)), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def alias_tokens(alias: str) -> tuple[str, ...]:
    return tuple(token.value for token in tokenize(normalize_text(alias)))
