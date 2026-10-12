from __future__ import annotations

from bisect import bisect_left
from itertools import product
from pathlib import Path
import re

from .law_index import LawAliasIndex
from .models import LawMention, ParsedLawLink, ReferenceGroup, Requisite
from .normalizer import normalize_text
from .requisites import extract_requisites


_ABBREVIATIONS = {
    "ст",
    "п",
    "пп",
    "ч",
    "рф",
    "фз",
    "ред",
    "г",
}
_RIGHT_PREFIX_RE = re.compile(
    r"^[\s,:()\-]*(?:(?:в|по|из|согласно|включая)\s+)?$",
    re.IGNORECASE,
)
# Requisites this close to the next law name are its left-hand context.
_LEFT_CONTEXT_GAP = 55


class _Sentences:
    """Sentence boundaries of one text, computed once in a single pass."""

    def __init__(self, text: str) -> None:
        self.length = len(text)
        self.boundaries = [index for index in range(len(text)) if _is_boundary(text, index)]

    def start(self, position: int) -> int:
        number = bisect_left(self.boundaries, position)
        return self.boundaries[number - 1] + 1 if number else 0

    def end(self, position: int) -> int:
        number = bisect_left(self.boundaries, position)
        return self.boundaries[number] if number < len(self.boundaries) else self.length


def _is_boundary(text: str, index: int) -> bool:
    char = text[index]
    if char in "!?;":
        return True
    if char != ".":
        return False
    previous = text[index - 1] if index else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False
    word_start = index
    while word_start and ("a" <= text[word_start - 1] <= "z" or "а" <= text[word_start - 1] <= "я"):
        word_start -= 1
    if text[word_start:index] in _ABBREVIATIONS:
        return False
    return not following or following.isspace()


class LawReferenceDetector:
    def __init__(self, aliases_path: str | Path) -> None:
        self.index = LawAliasIndex.from_json(aliases_path)

    def detect(self, text: str) -> list[ParsedLawLink]:
        normalized = normalize_text(text)
        if not normalized:
            return []
        sentences = _Sentences(normalized)
        mentions = self.index.find(normalized)
        mentions = self._add_fuzzy_mentions(normalized, mentions, sentences)
        links: list[ParsedLawLink] = []
        for mention_index, mention in enumerate(mentions):
            previous_end = mentions[mention_index - 1].end if mention_index else 0
            next_start = mentions[mention_index + 1].start if mention_index + 1 < len(mentions) else len(normalized)
            links.extend(self._parse_mention(normalized, mention, previous_end, next_start, sentences))
        return self._deduplicate(links)

    def _add_fuzzy_mentions(
        self,
        text: str,
        exact_mentions: list[LawMention],
        sentences: _Sentences,
    ) -> list[LawMention]:
        requisites = extract_requisites(text)
        fuzzy: list[LawMention] = []
        for requisite in requisites:
            sentence_end = sentences.end(requisite.end)
            if any(
                requisite.end <= mention.start <= requisite.end + 450 and mention.start < sentence_end
                for mention in exact_mentions
            ):
                continue
            fragment_end = min(sentence_end, requisite.end + 350)
            fragment = text[requisite.end:fragment_end]
            mention = self.index.find_fuzzy(fragment, requisite.end)
            if mention is None:
                continue
            if any(mention.start < item.end and item.start < mention.end for item in exact_mentions + fuzzy):
                continue
            fuzzy.append(mention)
        return sorted(exact_mentions + fuzzy, key=lambda item: item.start)

    def _parse_mention(
        self,
        text: str,
        mention: LawMention,
        previous_law_end: int,
        next_law_start: int,
        sentences: _Sentences,
    ) -> list[ParsedLawLink]:
        sentence_start = sentences.start(mention.start)
        sentence_end = sentences.end(mention.end)
        left_start = max(previous_law_end, sentence_start, mention.start - 450)
        right_end = min(next_law_start, sentence_end, mention.end + 180)

        left_requisites = extract_requisites(text[left_start : mention.start], left_start)
        # A legal requisite must directly introduce the law name. This prevents
        # stale markers earlier in a long sentence from leaking into a match.
        if left_requisites and mention.start - left_requisites[-1].end > _LEFT_CONTEXT_GAP:
            left_requisites = []

        groups = self._groups_before_law(left_requisites, mention.start)

        right_fragment = text[mention.end:right_end]
        right_requisites = extract_requisites(right_fragment, mention.end)
        if right_requisites:
            prefix = text[mention.end : right_requisites[0].start]
            if right_requisites[0].start - mention.end > 45 or not _RIGHT_PREFIX_RE.fullmatch(prefix):
                right_requisites = []
        if right_requisites and right_end == next_law_start and next_law_start <= sentence_end:
            # "ст. 105 УК РФ, ч. 2 ст. 158 УК РФ": the trailing requisites
            # introduce the next law, as reverse order is the norm.
            if next_law_start - right_requisites[-1].end <= _LEFT_CONTEXT_GAP:
                right_requisites = []
        if groups and any(item.kind == "article" for item in right_requisites):
            right_requisites = []

        if groups and right_requisites:
            self._attach_trailing_requisites(groups[-1], right_requisites)
        elif not groups and right_requisites:
            groups = self._groups_after_law(right_requisites)

        if not groups:
            return []

        context_start = max(0, mention.start - 260)
        context_end = min(len(text), mention.end + 260)
        law_id = self.index.resolve(mention, text[context_start:context_end])
        links: list[ParsedLawLink] = []
        for group in groups:
            if not (group.articles or group.points or group.subpoints):
                continue
            articles = group.articles or [None]
            points = group.points or [None]
            subpoints = group.subpoints or [None]
            for article, point, subpoint in product(articles, points, subpoints):
                links.append(
                    ParsedLawLink(
                        law_id=law_id,
                        article=article,
                        point_article=point,
                        subpoint_article=subpoint,
                        position=group.start,
                    )
                )
        return links

    @staticmethod
    def _groups_before_law(requisites: list[Requisite], law_start: int) -> list[ReferenceGroup]:
        if not requisites:
            return []
        article_indexes = [index for index, item in enumerate(requisites) if item.kind == "article"]
        if not article_indexes:
            return [LawReferenceDetector._group_from(requisites)]

        groups: list[ReferenceGroup] = []
        previous_article_index = -1
        for article_index in article_indexes:
            article = requisites[article_index]
            preceding = requisites[previous_article_index + 1 : article_index]
            group = LawReferenceDetector._group_from(preceding)
            group.articles.extend(article.values)
            group.start = preceding[0].start if preceding else article.start
            group.end = article.end
            groups.append(group)
            previous_article_index = article_index

        trailing = requisites[article_indexes[-1] + 1 :]
        if trailing:
            LawReferenceDetector._attach_trailing_requisites(groups[-1], trailing)
            groups[-1].end = trailing[-1].end
        return groups

    @staticmethod
    def _groups_after_law(requisites: list[Requisite]) -> list[ReferenceGroup]:
        article_indexes = [index for index, item in enumerate(requisites) if item.kind == "article"]
        if not article_indexes:
            return [LawReferenceDetector._group_from(requisites)]

        groups: list[ReferenceGroup] = []
        for number, article_index in enumerate(article_indexes):
            next_index = article_indexes[number + 1] if number + 1 < len(article_indexes) else len(requisites)
            article = requisites[article_index]
            following = requisites[article_index + 1 : next_index]
            group = LawReferenceDetector._group_from(following)
            group.articles.extend(article.values)
            group.start = article.start
            group.end = following[-1].end if following else article.end
            groups.append(group)
        return groups

    @staticmethod
    def _group_from(requisites: list[Requisite]) -> ReferenceGroup:
        group = ReferenceGroup()
        if requisites:
            group.start = requisites[0].start
            group.end = requisites[-1].end
        for requisite in requisites:
            target = group.points if requisite.kind == "point" else group.subpoints if requisite.kind == "subpoint" else group.articles
            target.extend(value for value in requisite.values if value not in target)
        return group

    @staticmethod
    def _attach_trailing_requisites(group: ReferenceGroup, requisites: list[Requisite]) -> None:
        for requisite in requisites:
            if requisite.kind == "article":
                continue
            target = group.points if requisite.kind == "point" else group.subpoints
            for value in requisite.values:
                if value not in target:
                    target.append(value)

    @staticmethod
    def _deduplicate(links: list[ParsedLawLink]) -> list[ParsedLawLink]:
        result: list[ParsedLawLink] = []
        seen: set[tuple[int, str | None, str | None, str | None]] = set()
        for link in sorted(links, key=lambda item: item.position):
            if link.key in seen:
                continue
            seen.add(link.key)
            result.append(link)
        return result


__all__ = ["LawReferenceDetector"]
