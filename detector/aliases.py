from __future__ import annotations

import re

from .normalizer import alias_tokens


_NUMBER_DATE_RE = re.compile(r"^(?P<kind>.+?) №(?P<number>\S+) от (?P<date>\d{2}\.\d{2}\.\d{4})(?P<rest>.*)$")
_KIND_NUMBER_RE = re.compile(r"^.+? №(?P<number>\S+)$")
# Bare numbers are only safe with a letter suffix: "№ 4" may be a hall or an appendix.
_LETTER_NUMBER_RE = re.compile(r"^\d+-[A-Za-zА-Яа-я]+$")
_FEDERAL_NUMBER_RE = re.compile(r"^(?P<base>\d+)-(?P<suffix>ФЗ|ФКЗ)$", re.IGNORECASE)
_ABBREVIATION_RE = re.compile(r"^(?P<abbr>[A-Za-zА-Яа-я]{2,6}) РФ$")


def expand_aliases(aliases: dict[int, list[str]]) -> dict[int, list[str]]:
    """Add spellings common in legal texts but absent from the dictionary."""
    owners: dict[tuple[str, ...], set[int]] = {}
    for law_id, variants in aliases.items():
        for alias in variants:
            owners.setdefault(alias_tokens(alias), set()).add(law_id)

    expanded: dict[int, list[str]] = {}
    for law_id, variants in aliases.items():
        extra: list[str] = []
        for alias in variants:
            match = _NUMBER_DATE_RE.match(alias)
            if match:
                kind, number, date, rest = match.group("kind", "number", "date", "rest")
                extra.append(f"{kind} от {date} №{number}{rest}")
                extra.append(f"{kind} от {date} №{number}")

            match = _KIND_NUMBER_RE.match(alias)
            if match and _LETTER_NUMBER_RE.match(match.group("number")):
                number = match.group("number")
                extra.append(f"№{number}")
                federal = _FEDERAL_NUMBER_RE.match(number)
                if federal:
                    extra.append(number)
                    extra.append(f"{federal.group('suffix')}-{federal.group('base')}")

            match = _ABBREVIATION_RE.match(alias)
            if match and sum(char.isupper() for char in match.group("abbr")) >= 2:
                abbreviation = match.group("abbr")
                for candidate in (abbreviation, f"{abbreviation}РФ"):
                    if owners.get(alias_tokens(candidate), {law_id}) == {law_id}:
                        extra.append(candidate)

        known = set(variants)
        expanded[law_id] = variants + [alias for alias in dict.fromkeys(extra) if alias not in known]
    return expanded


__all__ = ["expand_aliases"]
