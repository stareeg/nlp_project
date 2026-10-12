from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from .models import LawMention, Token
from .normalizer import alias_tokens, normalize_text, tokenize


@dataclass
class _Node:
    children: dict[str, int] = field(default_factory=dict)
    fail: int = 0
    outputs: list[tuple[tuple[str, ...], tuple[int, ...], str]] = field(default_factory=list)


@dataclass(frozen=True)
class LawMetadata:
    numbers: frozenset[str]
    dates: frozenset[str]


class LawAliasIndex:
    """Token-level Aho-Corasick index for all supplied law aliases."""

    def __init__(self, aliases: dict[str, list[str]]) -> None:
        self.aliases = {int(key): values for key, values in aliases.items()}
        self.nodes: list[_Node] = [_Node()]
        self.metadata: dict[int, LawMetadata] = {}
        grouped: dict[tuple[str, ...], set[int]] = {}
        display: dict[tuple[str, ...], str] = {}

        for law_id, variants in self.aliases.items():
            normalized_variants = [normalize_text(value) for value in variants]
            numbers: set[str] = set()
            dates: set[str] = set()
            for normalized in normalized_variants:
                numbers.update(re.findall(r"№\d+(?:[-/][\da-zа-я]+)*", normalized))
                dates.update(re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b", normalized))
            self.metadata[law_id] = LawMetadata(frozenset(numbers), frozenset(dates))

            for alias in variants:
                key = alias_tokens(alias)
                if not key:
                    continue
                grouped.setdefault(key, set()).add(law_id)
                if key not in display or len(alias) > len(display[key]):
                    display[key] = alias

        for key, law_ids in grouped.items():
            self._insert(key, tuple(sorted(law_ids)), display[key])
        self._build_failures()
        self._fuzzy_entries: list[tuple[tuple[str, ...], tuple[int, ...], str]] = []
        self._fuzzy_postings: dict[str, list[int]] = {}
        for key, law_ids in grouped.items():
            if not 2 <= len(key) <= 24:
                continue
            entry_index = len(self._fuzzy_entries)
            self._fuzzy_entries.append((key, tuple(sorted(law_ids)), display[key]))
            for token in set(key):
                self._fuzzy_postings.setdefault(token, []).append(entry_index)

    @classmethod
    def from_json(cls, path: str | Path) -> "LawAliasIndex":
        with open(path, encoding="utf-8") as source:
            return cls(json.load(source))

    def _insert(self, tokens: tuple[str, ...], law_ids: tuple[int, ...], alias: str) -> None:
        state = 0
        for token in tokens:
            next_state = self.nodes[state].children.get(token)
            if next_state is None:
                next_state = len(self.nodes)
                self.nodes[state].children[token] = next_state
                self.nodes.append(_Node())
            state = next_state
        self.nodes[state].outputs.append((tokens, law_ids, alias))

    def _build_failures(self) -> None:
        queue: deque[int] = deque()
        for child in self.nodes[0].children.values():
            queue.append(child)
        while queue:
            state = queue.popleft()
            for token, child in self.nodes[state].children.items():
                queue.append(child)
                failure = self.nodes[state].fail
                while failure and token not in self.nodes[failure].children:
                    failure = self.nodes[failure].fail
                self.nodes[child].fail = self.nodes[failure].children.get(token, 0)
                self.nodes[child].outputs.extend(self.nodes[self.nodes[child].fail].outputs)

    def find(self, normalized_text: str) -> list[LawMention]:
        tokens = tokenize(normalized_text)
        candidates = self._find_candidates(tokens)
        return self._select_non_overlapping(candidates)

    def find_fuzzy(self, fragment: str, offset: int = 0) -> LawMention | None:
        """Find one near-exact alias at the beginning of an anchored fragment.

        This is intentionally conservative and is only called after a legal
        requisite when exact matching failed. At least one alias token must
        still be present, so arbitrary prose never triggers a full scan.
        """
        query = tokenize(fragment)
        if len(query) < 2:
            return None
        query = query[:24]
        candidate_indexes: set[int] = set()
        for token in query:
            postings = self._fuzzy_postings.get(token.value, ())
            if len(postings) <= 2500:
                candidate_indexes.update(postings)
        if not candidate_indexes:
            return None

        scored: list[tuple[float, int, tuple[int, ...], str, int]] = []
        for entry_index in candidate_indexes:
            alias_value, law_ids, alias = self._fuzzy_entries[entry_index]
            size = len(alias_value)
            if size > len(query):
                continue
            query_value = " ".join(token.value for token in query[:size])
            alias_text = " ".join(alias_value)
            score = SequenceMatcher(None, query_value, alias_text, autojunk=False).ratio()
            scored.append((score, size, law_ids, alias, entry_index))
        if not scored:
            return None
        scored.sort(reverse=True, key=lambda item: (item[0], item[1], -len(item[2])))
        best = scored[0]
        second_score = next((item[0] for item in scored[1:] if item[2] != best[2]), 0.0)
        if best[0] < 0.89 or best[0] - second_score < 0.015:
            return None
        size = best[1]
        return LawMention(
            start=offset + query[0].start,
            end=offset + query[size - 1].end,
            token_start=0,
            token_end=size,
            law_ids=best[2],
            alias=best[3],
            token_count=size,
        )

    def _find_candidates(self, tokens: list[Token]) -> list[LawMention]:
        candidates: list[LawMention] = []
        state = 0
        for index, token in enumerate(tokens):
            while state and token.value not in self.nodes[state].children:
                state = self.nodes[state].fail
            state = self.nodes[state].children.get(token.value, 0)
            for alias_tokens_value, law_ids, alias in self.nodes[state].outputs:
                start_index = index - len(alias_tokens_value) + 1
                if start_index < 0:
                    continue
                candidates.append(
                    LawMention(
                        start=tokens[start_index].start,
                        end=token.end,
                        token_start=start_index,
                        token_end=index + 1,
                        law_ids=law_ids,
                        alias=alias,
                        token_count=len(alias_tokens_value),
                    )
                )
        return candidates

    @staticmethod
    def _select_non_overlapping(candidates: list[LawMention]) -> list[LawMention]:
        # Long, specific aliases win over abbreviations embedded in them.
        ranked = sorted(
            candidates,
            key=lambda item: (
                -item.token_count,
                -(item.end - item.start),
                len(item.law_ids),
                item.start,
            ),
        )
        selected: list[LawMention] = []
        for candidate in ranked:
            if any(candidate.start < other.end and other.start < candidate.end for other in selected):
                continue
            selected.append(candidate)
        return sorted(selected, key=lambda item: item.start)

    def resolve(self, mention: LawMention, context: str) -> int:
        if len(mention.law_ids) == 1:
            return mention.law_ids[0]

        normalized_context = normalize_text(context)
        scored: list[tuple[int, int, int]] = []
        for law_id in mention.law_ids:
            metadata = self.metadata[law_id]
            number_score = sum(number in normalized_context for number in metadata.numbers)
            date_score = sum(date in normalized_context for date in metadata.dates)
            scored.append((number_score * 10 + date_score * 20, -law_id, law_id))
        return max(scored)[2]


__all__ = ["LawAliasIndex"]
