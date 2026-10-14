from __future__ import annotations

import re

from .normalizer import alias_tokens


# добавляем к словарю написания, которые часто встречаются в текстах, но которых в нём нет
NUMBER_DATE_RE = re.compile(r"^(?P<kind>.+?) №(?P<number>\S+) от (?P<date>\d{2}\.\d{2}\.\d{4})(?P<rest>.*)$")
KIND_NUMBER_RE = re.compile(r"^.+? №(?P<number>\S+)$")
# голый номер берём только с буквами ("152-ФЗ"), а "№ 4" может быть номером зала
LETTER_NUMBER_RE = re.compile(r"^\d+-[A-Za-zА-Яа-я]+$")
FEDERAL_NUMBER_RE = re.compile(r"^(?P<base>\d+)-(?P<suffix>ФЗ|ФКЗ)$", re.IGNORECASE)
ABBREVIATION_RE = re.compile(r"^(?P<abbr>[A-Za-zА-Яа-я]{2,6}) РФ$")

# общепринятые сокращения, которых нет в словаре; закон ищем по полному названию, а не по id
EXTRA_ALIASES = {
    "Градостроительный кодекс": ["ГрК РФ", "ГрК России", "ГрК", "ГрКРФ"],
    "Кодекс административного судопроизводства": ["КАС РФ", "КАС России", "КАС", "КАСРФ"],
    "Водный кодекс": ["ВК РФ", "ВК России", "ВК", "ВКРФ"],
    "Воздушный кодекс": ["ВзК РФ", "ВзК России", "ВзК", "ВзКРФ"],
    # "ТК ЕАЭС" - Таможенный, а не Трудовой; более длинный алиас перебивает "ТК"
    "Таможенный кодекс": [
        "ТК ЕАЭС", "ТК ТС", "Таможенный кодекс ЕАЭС", "Таможенный кодекс Таможенного союза",
        "Таможенный кодекс Евразийского экономического союза",
    ],
}


def expand_aliases(aliases: dict[int, list[str]]) -> dict[int, list[str]]:
    owners: dict[tuple[str, ...], set[int]] = {}
    for law_id, variants in aliases.items():
        for alias in variants:
            owners.setdefault(alias_tokens(alias), set()).add(law_id)

    by_name = {alias: law_id for law_id, variants in aliases.items() for alias in variants}
    manual: dict[int, list[str]] = {}
    for name, extra_aliases in EXTRA_ALIASES.items():
        law_id = by_name.get(name)
        if law_id is None:
            continue
        for alias in extra_aliases:
            if owners.get(alias_tokens(alias), {law_id}) == {law_id}:
                manual.setdefault(law_id, []).append(alias)

    result: dict[int, list[str]] = {}
    for law_id, variants in aliases.items():
        extra: list[str] = list(manual.get(law_id, []))
        for alias in variants:
            # "Федеральный закон №152-ФЗ от 27.07.2006" -> "Федеральный закон от 27.07.2006 №152-ФЗ"
            m = NUMBER_DATE_RE.match(alias)
            if m:
                extra.append(f"{m['kind']} от {m['date']} №{m['number']}{m['rest']}")
                extra.append(f"{m['kind']} от {m['date']} №{m['number']}")

            # "№152-ФЗ", "152-ФЗ", "ФЗ-152"
            m = KIND_NUMBER_RE.match(alias)
            if m and LETTER_NUMBER_RE.match(m["number"]):
                extra.append(f"№{m['number']}")
                federal = FEDERAL_NUMBER_RE.match(m["number"])
                if federal:
                    extra.append(m["number"])
                    extra.append(f"{federal['suffix']}-{federal['base']}")

            # "КоАП РФ" -> "КоАП", "КоАПРФ", если такое сокращение больше ни у кого не занято
            m = ABBREVIATION_RE.match(alias)
            if m and sum(char.isupper() for char in m["abbr"]) >= 2:
                for candidate in (m["abbr"], m["abbr"] + "РФ"):
                    if owners.get(alias_tokens(candidate), {law_id}) == {law_id}:
                        extra.append(candidate)

        known = set(variants)
        result[law_id] = variants + [alias for alias in dict.fromkeys(extra) if alias not in known]
    return result
