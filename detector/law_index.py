from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from .aliases import expand_aliases
from .models import LawMention, Token
from .normalizer import alias_tokens, normalize_text, tokenize


FUZZY_THRESHOLD = 0.89
FUZZY_MARGIN = 0.015
# кандидаты с похожестью ниже этой всё равно ни на что не влияют
FUZZY_FLOOR = FUZZY_THRESHOLD - FUZZY_MARGIN
REQUISITE_TOKENS = {"ст", "п", "пп", "подп", "ч", "абз", "пункт", "стат", "част", "подпункт"}


@dataclass
class Node:
    children: dict[str, int] = field(default_factory=dict)
    fail: int = 0
    outputs: list[tuple[tuple[str, ...], tuple[int, ...], str]] = field(default_factory=list)


class LawAliasIndex:
    # Ахо-Корасик по токенам: все алиасы ищутся за один проход по тексту
    def __init__(self, aliases: dict[str, list[str]]) -> None:
        self.aliases = expand_aliases({int(key): values for key, values in aliases.items()})
        self.nodes = [Node()]
        self.numbers: dict[int, set[str]] = {}
        self.dates: dict[int, set[str]] = {}
        laws_by_key: dict[tuple[str, ...], set[int]] = {}
        longest_alias: dict[tuple[str, ...], str] = {}

        for law_id, variants in self.aliases.items():
            self.numbers[law_id] = set()
            self.dates[law_id] = set()
            for alias in variants:
                normalized = normalize_text(alias)
                self.numbers[law_id].update(re.findall(r"№\d+(?:[-/][\da-zа-я]+)*", normalized))
                self.dates[law_id].update(re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b", normalized))
                key = alias_tokens(alias)
                if not key:
                    continue
                laws_by_key.setdefault(key, set()).add(law_id)
                if len(alias) > len(longest_alias.get(key, "")):
                    longest_alias[key] = alias

        for key, law_ids in laws_by_key.items():
            self.insert(key, tuple(sorted(law_ids)), longest_alias[key])
        self.build_fail_links()

        self.fuzzy_entries: list[tuple[tuple[str, ...], tuple[int, ...], str]] = []
        self.fuzzy_by_token: dict[str, list[int]] = {}
        self.fuzzy_by_letter: dict[str, set[int]] = {}
        for key, law_ids in laws_by_key.items():
            if not 2 <= len(key) <= 24:
                continue
            n = len(self.fuzzy_entries)
            self.fuzzy_entries.append((key, tuple(sorted(law_ids)), longest_alias[key]))
            for token in set(key):
                self.fuzzy_by_token.setdefault(token, []).append(n)
            self.fuzzy_by_letter.setdefault(key[0][0], set()).add(n)

    @classmethod
    def from_json(cls, path: str | Path) -> LawAliasIndex:
        with open(path, encoding="utf-8") as file:
            return cls(json.load(file))

    def insert(self, tokens: tuple[str, ...], law_ids: tuple[int, ...], alias: str) -> None:
        state = 0
        for token in tokens:
            if token not in self.nodes[state].children:
                self.nodes[state].children[token] = len(self.nodes)
                self.nodes.append(Node())
            state = self.nodes[state].children[token]
        self.nodes[state].outputs.append((tokens, law_ids, alias))

    def build_fail_links(self) -> None:
        queue = deque(self.nodes[0].children.values())
        while queue:
            state = queue.popleft()
            for token, child in self.nodes[state].children.items():
                queue.append(child)
                fail = self.nodes[state].fail
                while fail and token not in self.nodes[fail].children:
                    fail = self.nodes[fail].fail
                self.nodes[child].fail = self.nodes[fail].children.get(token, 0)
                self.nodes[child].outputs.extend(self.nodes[self.nodes[child].fail].outputs)

    def find(self, text: str) -> list[LawMention]:
        tokens = tokenize(text)
        return select_non_overlapping(self.find_all(tokens))

    def find_all(self, tokens: list[Token]) -> list[LawMention]:
        found: list[LawMention] = []
        state = 0
        for i, token in enumerate(tokens):
            while state and token.value not in self.nodes[state].children:
                state = self.nodes[state].fail
            state = self.nodes[state].children.get(token.value, 0)
            for key, law_ids, alias in self.nodes[state].outputs:
                first = i - len(key) + 1
                if first >= 0:
                    found.append(LawMention(tokens[first].start, token.end, first, i + 1, law_ids, alias, len(key)))
        return found

    def find_fuzzy(self, fragment: str, offset: int = 0) -> LawMention | None:
        # название с опечаткой в начале фрагмента, порог высокий, чтобы не придумать закон
        query = tokenize(fragment)
        if len(query) < 2:
            return None
        first = query[0].value
        if not first[0].isalpha() or first in REQUISITE_TOKENS:
            return None
        query = query[:24]
        candidates: set[int] = set()
        for token in query:
            entries = self.fuzzy_by_token.get(token.value, ())
            if len(entries) <= 2500:
                candidates.update(entries)
        # опечатка в первой букве бывает редко, а так кандидатов сильно меньше
        candidates &= self.fuzzy_by_letter.get(first[0], set())
        if not candidates:
            return None

        scored = []
        matcher = SequenceMatcher(None, autojunk=False)
        for n in candidates:
            key, law_ids, alias = self.fuzzy_entries[n]
            size = len(key)
            if size > len(query):
                continue
            matcher.set_seqs(" ".join(t.value for t in query[:size]), " ".join(key))
            if matcher.real_quick_ratio() < FUZZY_FLOOR or matcher.quick_ratio() < FUZZY_FLOOR:
                continue
            scored.append((matcher.ratio(), size, law_ids, alias))
        if not scored:
            return None
        scored.sort(reverse=True, key=lambda item: (item[0], item[1], -len(item[2])))
        score, size, law_ids, alias = scored[0]
        second = next((item[0] for item in scored[1:] if item[2] != law_ids), 0.0)
        if score < FUZZY_THRESHOLD or score - second < FUZZY_MARGIN:
            return None
        return LawMention(offset + query[0].start, offset + query[size - 1].end, 0, size, law_ids, alias, size)

    def resolve(self, mention: LawMention, context: str) -> int:
        # один алиас у нескольких законов: смотрим, есть ли рядом их номер или дата
        if len(mention.law_ids) == 1:
            return mention.law_ids[0]
        context = normalize_text(context)

        def score(law_id: int) -> tuple[int, int]:
            numbers = sum(number in context for number in self.numbers[law_id])
            dates = sum(date in context for date in self.dates[law_id])
            return numbers * 10 + dates * 20, -law_id

        return max(mention.law_ids, key=score)


def select_non_overlapping(found: list[LawMention]) -> list[LawMention]:
    # длинное название важнее короткого сокращения внутри него
    ranked = sorted(found, key=lambda m: (-m.token_count, -(m.end - m.start), len(m.law_ids), m.start))
    selected: list[LawMention] = []
    for mention in ranked:
        if not any(mention.start < other.end and other.start < mention.end for other in selected):
            selected.append(mention)
    return sorted(selected, key=lambda m: m.start)
