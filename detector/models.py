from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class LawMention:
    start: int
    end: int
    token_start: int
    token_end: int
    law_ids: tuple[int, ...]
    alias: str
    token_count: int


@dataclass(frozen=True)
class Requisite:
    kind: str
    values: tuple[str, ...]
    start: int
    end: int


@dataclass
class ReferenceGroup:
    articles: list[str] = field(default_factory=list)
    points: list[str] = field(default_factory=list)
    subpoints: list[str] = field(default_factory=list)
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class ParsedLawLink:
    law_id: int
    article: str | None = None
    point_article: str | None = None
    subpoint_article: str | None = None
    position: int = 0

    @property
    def key(self) -> tuple[int, str | None, str | None, str | None]:
        return self.law_id, self.article, self.point_article, self.subpoint_article
