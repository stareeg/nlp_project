from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

from .models import Token


DASHES = str.maketrans({char: "-" for char in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})
QUOTES = str.maketrans({"«": '"', "»": '"', "„": '"', "“": '"', "”": '"', "‟": '"', "‘": "'", "’": "'"})
PUNCTUATION = {**DASHES, **QUOTES}
# латинские буквы, похожие на русские ("CК РФ" в словаре набрано с латинской C)
HOMOGLYPHS = str.maketrans("aceopxykmtbh", "асеорхукмтвн")
# слово целиком, а смешение алфавитов проверяем внутри: старый вариант
# "[a-zа-я]*(?:[a-z][а-я]|[а-я][a-z])[a-zа-я]*" был квадратичным на длинных словах
LETTERS_RE = re.compile(r"[a-zа-я]+")
LATIN_RE = re.compile(r"[a-z]")
CYRILLIC_RE = re.compile(r"[а-я]")
SPACE_RE = re.compile(r"[\s\u00a0\u2007\u202f]+")
NUMBER_SIGN_RE = re.compile(r"(?<![\wа-я])(?:no|n)\.?\s*(?=\d)")
NUMBER_SPACE_RE = re.compile(r"№\s+(?=\d)")
# сокращения кодексов, которые пишут через дефис, точки или пробелы: "УК-РФ", "У.К. РФ", "Н К РФ"
CODE_ABBREVIATIONS = {
    "апк", "бк", "вк", "взк", "гк", "гпк", "грк", "жк", "зк", "кас", "коап", "лк", "нк", "ск",
    "тк", "ук", "уик", "упк",
}
CODE_HYPHEN_RE = re.compile(r"(?<![а-я])(" + "|".join(sorted(CODE_ABBREVIATIONS)) + r")-(рф|россии)(?![а-я])")
SPLIT_CODE_RE = re.compile(r"(?<![а-я])(?:[а-я](?:\.\s?|\s)){1,3}[а-я]\.?(?=\s?(?:рф|россии)(?![а-я]))")
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


def fix_mixed_word(match: re.Match) -> str:
    word = match.group(0)
    if LATIN_RE.search(word) and CYRILLIC_RE.search(word):
        return word.translate(HOMOGLYPHS)
    return word


def join_split_code(match: re.Match) -> str:
    joined = re.sub(r"[.\s]", "", match.group(0))
    return joined + " " if joined in CODE_ABBREVIATIONS else match.group(0)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(PUNCTUATION)
    text = text.casefold().replace("ё", "е")
    text = LETTERS_RE.sub(fix_mixed_word, text)
    text = NUMBER_SIGN_RE.sub("№", text)
    text = NUMBER_SPACE_RE.sub("№", text)
    text = CODE_HYPHEN_RE.sub(r"\1 \2", text)
    text = SPLIT_CODE_RE.sub(join_split_code, text)
    return SPACE_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[Token]:
    return [Token(stem_token(m.group(0)), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def alias_tokens(alias: str) -> tuple[str, ...]:
    return tuple(token.value for token in tokenize(normalize_text(alias)))
