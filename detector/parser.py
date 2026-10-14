from __future__ import annotations

from bisect import bisect_left
import hashlib
from itertools import product
from pathlib import Path
import pickle
import re

from .law_index import LawAliasIndex
from .models import LawMention, ParsedLawLink, ReferenceGroup, Requisite
from .normalizer import normalize_text
from .requisites import extract_requisites


# сокращения, после которых точка не конец предложения
ABBREVIATIONS = {
    "ст", "п", "пп", "подп", "ч", "абз", "гл", "разд", "прил", "см", "утв", "им",
    "т", "д", "др", "рф", "фз", "ред", "г", "гг", "руб", "тыс", "млн",
}
RIGHT_PREFIX_RE = re.compile(r"^[\s,:()\-]*(?:(?:в|по|из|согласно|включая)\s+)?$")
SEPARATORS_RE = re.compile(r"[\s,;:()\-]*(?:(?:и|или|а также|также)[\s,;:()\-]*)*")
SAME_ARTICLE = r"(?:(?:той|этой)\s+же|указанной|этой|данной|названной)\s+стать(?:и|е|ей|ю)"
SAME_LAW = (
    r"(?:(?:(?:того|этого)\s+же|указанного|этого|данного|названного)\s+(?:федерального\s+)?(?:кодекса|закона)"
    r"|там\s+же)"
)
SAME_ARTICLE_RE = re.compile(SAME_ARTICLE)
SAME_LAW_RE = re.compile(SAME_LAW)
ANAPHORA_RE = re.compile(rf"{SAME_ARTICLE}|{SAME_LAW}")
ANAPHORA_AHEAD_RE = re.compile(rf"\s*(?:{SAME_ARTICLE}|{SAME_LAW})")
DIGIT_AHEAD_RE = re.compile(r"\s*\d")

# если реквизит дальше от названия закона, считаем что он не к нему
MAX_GAP = 55
LEFT_WINDOW = 450
RIGHT_WINDOW = 180


class Sentences:
    def __init__(self, text: str) -> None:
        self.length = len(text)
        self.bounds = [i for i in range(len(text)) if is_sentence_end(text, i)]

    def start(self, pos: int) -> int:
        i = bisect_left(self.bounds, pos)
        return self.bounds[i - 1] + 1 if i else 0

    def end(self, pos: int) -> int:
        i = bisect_left(self.bounds, pos)
        return self.bounds[i] if i < len(self.bounds) else self.length


def is_sentence_end(text: str, i: int) -> bool:
    char = text[i]
    if char == ";":
        # "ст. 10; 11 УК РФ": здесь точка с запятой разделяет номера, а не предложения
        return not (i and text[i - 1].isdigit() and DIGIT_AHEAD_RE.match(text, i + 1))
    if char in "!?":
        return True
    if char != ".":
        return False
    prev = text[i - 1] if i else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if prev.isdigit() and nxt.isdigit():
        return False
    word_start = i
    while word_start and ("a" <= text[word_start - 1] <= "z" or "а" <= text[word_start - 1] <= "я"):
        word_start -= 1
    if text[word_start:i] in ABBREVIATIONS:
        return False
    return not nxt or nxt.isspace()


class LawReferenceDetector:
    def __init__(self, aliases_path: str | Path) -> None:
        self.index = LawAliasIndex.from_json(aliases_path)

    @classmethod
    def cached(cls, aliases_path: str | Path) -> LawReferenceDetector:
        # индекс строится несколько секунд, поэтому сохраняем его рядом со словарём
        # и пересобираем, только если поменялся словарь или код детектора
        aliases_path = Path(aliases_path)
        cache_path = aliases_path.with_suffix(".index.pkl")
        digest = hashlib.sha256(aliases_path.read_bytes())
        for source in sorted(Path(__file__).parent.glob("*.py")):
            digest.update(source.read_bytes())
        key = digest.hexdigest()

        if cache_path.exists():
            with open(cache_path, "rb") as file:
                if pickle.load(file) == key:
                    return pickle.load(file)

        detector = cls(aliases_path)
        tmp_path = cache_path.with_name(cache_path.name + ".tmp")
        try:
            with open(tmp_path, "wb") as file:
                pickle.dump(key, file)
                pickle.dump(detector, file, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_path.replace(cache_path)
        except OSError:
            # нет прав на запись - работаем без кеша
            pass
        return detector

    def detect(self, text: str) -> list[ParsedLawLink]:
        text = normalize_text(text)
        if not text:
            return []
        sentences = Sentences(text)
        mentions = self.index.find(text)
        mentions = self.add_fuzzy_mentions(text, mentions, sentences)
        links: list[ParsedLawLink] = []
        for i, mention in enumerate(mentions):
            prev_end = mentions[i - 1].end if i else 0
            next_start = mentions[i + 1].start if i + 1 < len(mentions) else None
            links.extend(self.parse_mention(text, mention, prev_end, next_start, sentences))
        links.extend(self.anaphora_links(text, links, sentences))
        return deduplicate(links)

    def add_fuzzy_mentions(self, text: str, exact: list[LawMention], sentences: Sentences) -> list[LawMention]:
        # ищем название с опечаткой только сразу после реквизита, где точного совпадения нет
        requisites = extract_requisites(text)
        starts = [m.start for m in exact]
        fuzzy: list[LawMention] = []
        for i, req in enumerate(requisites):
            sentence_end = sentences.end(req.end)
            j = bisect_left(starts, req.end)
            if j < len(exact) and starts[j] <= sentence_end:
                if only_requisites_between(text, requisites[i + 1 :], req.end, starts[j]):
                    continue
            fragment = text[req.end : min(sentence_end, req.end + 350)]
            mention = self.index.find_fuzzy(fragment, req.end)
            if mention is None:
                continue
            if any(mention.start < m.end and m.start < mention.end for m in exact + fuzzy):
                continue
            fuzzy.append(mention)
        return sorted(exact + fuzzy, key=lambda m: m.start)

    def parse_mention(
        self,
        text: str,
        mention: LawMention,
        prev_law_end: int,
        next_law_start: int | None,
        sentences: Sentences,
    ) -> list[ParsedLawLink]:
        sentence_start = sentences.start(mention.start)
        sentence_end = sentences.end(mention.end)
        left_start = max(prev_law_end, sentence_start, mention.start - LEFT_WINDOW)
        # "п. 3 указанной статьи и ст. 5 ГК РФ": п. 3 уже относится к прошлой статье
        for match in ANAPHORA_RE.finditer(text, left_start, mention.start):
            left_start = match.end()
        right_end = min(len(text) if next_law_start is None else next_law_start, sentence_end, mention.end + RIGHT_WINDOW)

        left = extract_requisites(text[left_start : mention.start], left_start)
        if left and mention.start - left[-1].end > MAX_GAP:
            left = []
        groups = groups_before_law(left)

        right = extract_requisites(text[mention.end : right_end], mention.end)
        if right:
            prefix = text[mention.end : right[0].start]
            if right[0].start - mention.end > 45 or not RIGHT_PREFIX_RE.fullmatch(prefix):
                right = []
        # "ст. 105 УК РФ, ч. 2 ст. 158 УК РФ": ч. 2 относится к следующему закону
        if right and next_law_start is not None and right_end == next_law_start <= sentence_end:
            if next_law_start - right[-1].end <= MAX_GAP:
                right = []
        if right and ANAPHORA_AHEAD_RE.match(text, right[-1].end):
            right = []
        if groups and any(r.kind == "article" for r in right):
            right = []

        if groups and right:
            attach_trailing(groups[-1], right)
        elif right:
            groups = groups_after_law(right)
        if not groups:
            return []

        context = text[max(0, mention.start - 260) : mention.end + 260]
        law_id = self.index.resolve(mention, context)
        return [link for group in groups for link in group_links(group, law_id)]

    def anaphora_links(self, text: str, links: list[ParsedLawLink], sentences: Sentences) -> list[ParsedLawLink]:
        # "п. 3 указанной статьи", "ст. 11 того же кодекса"
        result: list[ParsedLawLink] = []
        for regex, same_article in ((SAME_ARTICLE_RE, True), (SAME_LAW_RE, False)):
            for match in regex.finditer(text):
                before = [link for link in links + result if link.position < match.start()]
                if not before:
                    continue
                anchor = max(before, key=lambda link: link.position)
                chain = chain_before(text, match.start(), sentences)
                if not chain:
                    continue
                if same_article:
                    if anchor.article is None or any(r.kind == "article" for r in chain):
                        continue
                    group = group_from(chain)
                    group.articles = [anchor.article]
                    groups = [group]
                else:
                    groups = groups_before_law(chain)
                for group in groups:
                    result.extend(group_links(group, anchor.law_id))
        return result


def only_requisites_between(text: str, requisites: list[Requisite], start: int, end: int) -> bool:
    pieces: list[str] = []
    pos = start
    for req in requisites:
        if req.start >= end:
            break
        pieces.append(text[pos : req.start])
        pos = max(pos, req.end)
    pieces.append(text[pos:end])
    return SEPARATORS_RE.fullmatch(" ".join(pieces)) is not None


def chain_before(text: str, end: int, sentences: Sentences) -> list[Requisite]:
    start = max(sentences.start(end), end - 200)
    requisites = extract_requisites(text[start:end], start)
    chain: list[Requisite] = []
    border = end
    for req in reversed(requisites):
        if not SEPARATORS_RE.fullmatch(text[req.end : border]):
            break
        chain.insert(0, req)
        border = req.start
    return chain


def groups_before_law(requisites: list[Requisite]) -> list[ReferenceGroup]:
    if not requisites:
        return []
    article_idx = [i for i, r in enumerate(requisites) if r.kind == "article"]
    if not article_idx:
        return [group_from(requisites)]

    groups: list[ReferenceGroup] = []
    prev = -1
    for i in article_idx:
        preceding = requisites[prev + 1 : i]
        group = group_from(preceding)
        group.articles.extend(requisites[i].values)
        group.start = preceding[0].start if preceding else requisites[i].start
        groups.append(group)
        prev = i
    trailing = requisites[article_idx[-1] + 1 :]
    if trailing:
        attach_trailing(groups[-1], trailing)
    return groups


def groups_after_law(requisites: list[Requisite]) -> list[ReferenceGroup]:
    article_idx = [i for i, r in enumerate(requisites) if r.kind == "article"]
    if not article_idx:
        return [group_from(requisites)]

    groups: list[ReferenceGroup] = []
    for n, i in enumerate(article_idx):
        next_i = article_idx[n + 1] if n + 1 < len(article_idx) else len(requisites)
        group = group_from(requisites[i + 1 : next_i])
        group.articles.extend(requisites[i].values)
        group.start = requisites[i].start
        groups.append(group)
    return groups


def group_from(requisites: list[Requisite]) -> ReferenceGroup:
    group = ReferenceGroup()
    if requisites:
        group.start = requisites[0].start
    for req in requisites:
        add_values(group, req)
    return group


def attach_trailing(group: ReferenceGroup, requisites: list[Requisite]) -> None:
    for req in requisites:
        if req.kind != "article":
            add_values(group, req)


def add_values(group: ReferenceGroup, req: Requisite) -> None:
    target = {
        "article": group.articles,
        "part": group.parts,
        "point": group.points,
        "subpoint": group.subpoints,
    }[req.kind]
    target.extend(value for value in req.values if value not in target)


def group_links(group: ReferenceGroup, law_id: int) -> list[ParsedLawLink]:
    points, subpoints = group.points, group.subpoints
    if group.parts:
        if points and not subpoints:
            # "пункт 2 части 1 статьи 7": часть идёт в point_article, пункт в subpoint_article
            points, subpoints = group.parts, group.points
        else:
            points = group.parts + [p for p in points if p not in group.parts]
    if not (group.articles or points or subpoints):
        return []
    return [
        ParsedLawLink(law_id, article, point, subpoint, group.start)
        for article, point, subpoint in product(group.articles or [None], points or [None], subpoints or [None])
    ]


def deduplicate(links: list[ParsedLawLink]) -> list[ParsedLawLink]:
    result: list[ParsedLawLink] = []
    seen: set[tuple] = set()
    for link in sorted(links, key=lambda link: link.position):
        if link.key not in seen:
            seen.add(link.key)
            result.append(link)
    return result
