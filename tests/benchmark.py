"""Graded benchmark with gold labels.

Four levels of 250 texts each, from single abbreviated references to long
texts with chains of references, inflected names, lists and noisy formats.

    python tests/benchmark.py                          # in-process detector
    python tests/benchmark.py --url http://localhost:8978/detect
    python tests/benchmark.py --errors 20              # print failed texts
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES_PER_LEVEL = 250
Link = tuple  # (law_id, article, point_article, subpoint_article)

LAWS_SHORT = {
    15: ["НК РФ", "НК России"],
    13: ["УК РФ"],
    5: ["ГК РФ"],
    10: ["ТК РФ"],
    0: ["АПК РФ"],
    6: ["ГПК РФ"],
    12: ["УПК РФ"],
    7: ["ЖК РФ"],
    16: ["ЗК РФ"],
    1: ["БК РФ"],
    17: ["КоАП РФ"],
}
LAWS_FULL = {
    15: ["Налогового кодекса РФ", "Налогового кодекса Российской Федерации", "Налогового Кодекса"],
    13: ["Уголовного кодекса РФ", "Уголовного кодекса Российской Федерации"],
    5: ["Гражданского кодекса РФ", "Гражданского кодекса Российской Федерации"],
    10: ["Трудового кодекса Российской Федерации", "Трудового кодекса РФ"],
    0: ["Арбитражного процессуального кодекса РФ"],
    6: ["Гражданского процессуального кодекса Российской Федерации"],
    12: ["Уголовно-процессуального кодекса РФ"],
    7: ["Жилищного кодекса Российской Федерации"],
    16: ["Земельного кодекса РФ"],
    17: ["Кодекса РФ об административных правонарушениях",
         "Кодекса Российской Федерации об административных правонарушениях"],
    330: ["Федерального закона «О персональных данных»",
          "Федерального закона №152-ФЗ от 27.07.2006 «О персональных данных»",
          "ФЗ «О персональных данных»"],
    249: ["Федерального закона «О полиции»", "ФЗ «О полиции»"],
    224: ["Федерального закона «О бухгалтерском учете»"],
    984: ["Закона «О защите прав потребителей»"],
}
# Formats from real legal texts that are not covered by the dictionary verbatim.
LAWS_HARD = {
    8: ["СК РФ", "Семейного кодекса РФ"],
    17: ["КоАП", "КоАП РФ"],
    330: ["Федерального закона от 27.07.2006 N 152-ФЗ", "Федерального закона от 27.07.2006 № 152-ФЗ «О персональных данных»",
          "Закона № 152-ФЗ", "ФЗ-152", "закона N 152-ФЗ"],
    13: ["УК РФ", "УКРФ", "Уголовного кодекса"],
    15: ["НК РФ", "Налогвого кодекса РФ", "Налогового кодекса"],
    5: ["ГК РФ", "Гражданского кодекса Росийской Федерации"],
}

# Case of the head word of a reference depends on the preceding preposition.
INTROS = [
    ("Согласно", "dat"),
    ("В соответствии с", "ins"),
    ("В силу", "gen"),
    ("На основании", "gen"),
    ("Как указано в", "pre"),
    ("Исходя из", "gen"),
]
HEADS = {
    "article": {"sg": {"gen": "статьи", "dat": "статье", "ins": "статьей", "pre": "статье"},
                "pl": {"gen": "статей", "dat": "статьям", "ins": "статьями", "pre": "статьях"}},
    "point": {"sg": {"gen": "пункта", "dat": "пункту", "ins": "пунктом", "pre": "пункте"},
              "pl": {"gen": "пунктов", "dat": "пунктам", "ins": "пунктами", "pre": "пунктах"}},
    "part": {"sg": {"gen": "части", "dat": "части", "ins": "частью", "pre": "части"},
             "pl": {"gen": "частей", "dat": "частям", "ins": "частями", "pre": "частях"}},
    "subpoint": {"sg": {"gen": "подпункта", "dat": "подпункту", "ins": "подпунктом", "pre": "подпункте"},
                 "pl": {"gen": "подпунктов", "dat": "подпунктам", "ins": "подпунктами", "pre": "подпунктах"}},
}
ABBR = {"article": "ст.", "point": "п.", "part": "ч.", "subpoint": "пп."}
GENITIVE = {"article": "статьи", "point": "пункта", "part": "части", "subpoint": "подпункта"}
LETTERS = "абвгдежзклмнопрт"
FILLERS = [
    "налогоплательщик обязан представить декларацию",
    "установлена ответственность за нарушение срока",
    "суд вправе снизить размер неустойки",
    "работодатель обязан выплатить компенсацию",
    "заявление подается в письменной форме",
    "срок исковой давности составляет три года",
    "решение может быть обжаловано",
    "оператор обязан обеспечить конфиденциальность сведений",
]
NOISE = [
    "Договор заключен 05.02.2024 сроком на 3 года.",
    "Сумма штрафа составила 15 000 рублей, что указано в приложении № 2.",
    "Заседание назначено на 10 часов 30 минут в зале № 4.",
    "Истец представил 12 документов на 45 листах.",
    "Ответчик возражал против иска.",
    "Пункт 7 повестки дня был перенесен.",
]


def _join(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " и " + values[-1]


class Builder:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)

    def article(self) -> str:
        roll = self.r.random()
        if roll < 0.15:
            return f"{self.r.randint(1, 40)}.{self.r.randint(1, 9)}"
        return str(self.r.randint(1, 450))

    def point(self) -> str:
        return str(self.r.randint(1, 12))

    def subpoint(self) -> str:
        if self.r.random() < 0.5:
            return self.r.choice(LETTERS)
        return str(self.r.randint(1, 15))

    def typo(self, word: str) -> str:
        """One adjacent swap or deletion inside the word."""
        while True:
            position = self.r.randint(1, len(word) - 3)
            if self.r.random() < 0.5:
                result = word[:position] + word[position + 1] + word[position] + word[position + 2 :]
            else:
                result = word[:position] + word[position + 1 :]
            if result != word:
                return result

    def values(self, make, count: int) -> list[str]:
        result: list[str] = []
        while len(result) < count:
            value = make()
            if value not in result:
                result.append(value)
        return result

    def reference(self, case: str | None, max_list: int = 1, part_word: bool | None = None, hard: bool = False):
        """Return (text, [(article, point, subpoint)]) for one reverse-order reference."""
        depth = self.r.choice([1, 1, 2, 2, 3])
        point_kind = "part" if (part_word if part_word is not None else self.r.random() < 0.3) else "point"
        list_level = self.r.randint(1, depth) if max_list > 1 and self.r.random() < 0.5 else 0
        levels = ["article", point_kind, "subpoint"][:depth][::-1]
        makers = {"article": self.article, point_kind: self.point, "subpoint": self.subpoint}
        values: dict[str, list[str]] = {}
        parts: list[str] = []
        for position, level in enumerate(levels):
            count = self.r.randint(2, max_list) if list_level and levels[position] == ["article", point_kind, "subpoint"][list_level - 1] else 1
            values[level] = self.values(makers[level], count)
            rendered_values = values[level]
            if hard and level == "subpoint" and rendered_values[0].isalpha() and self.r.random() < 0.6:
                rendered_values = [f"«{value}»" for value in rendered_values]
            if case is None:
                marker = ABBR[level]
                if hard and level == "subpoint" and self.r.random() < 0.4:
                    marker = "подп."
                if count > 1 and level == "article" and self.r.random() < 0.3:
                    marker = "ст.ст."
            else:
                number = "pl" if count > 1 else "sg"
                marker = HEADS[level][number][case] if position == 0 else GENITIVE[level]
                if count > 1 and position > 0:
                    marker = HEADS[level]["pl"]["gen"]
                if hard and len(marker) >= 6 and self.r.random() < 0.35:
                    marker = self.typo(marker)
            separator = "" if hard and case is None and self.r.random() < 0.3 else " "
            parts.append(f"{marker}{separator}{_join(rendered_values)}")
        links = []
        for article in values.get("article", [None]):
            for point in values.get(point_kind, [None]):
                for subpoint in values.get("subpoint", [None]):
                    links.append((article, point, subpoint))
        return " ".join(parts), links

    def law(self, pool: dict[int, list[str]]) -> tuple[int, str]:
        law_id = self.r.choice(list(pool))
        return law_id, self.r.choice(pool[law_id])

    def sentence(self, refs: int, pool, case_mode: str, max_list: int, hard: bool = False):
        intro, case = self.r.choice(INTROS)
        if case_mode == "abbr":
            case = None
        elif case_mode == "mixed" and self.r.random() < 0.5:
            case = None
        gold: set[Link] = set()
        chunks: list[str] = []
        shared_law = refs > 1 and self.r.random() < 0.3
        law_id, law_text = self.law(pool)
        for index in range(refs):
            text, links = self.reference(case, max_list, hard=hard)
            if not shared_law:
                law_id, law_text = self.law(pool)
            if not shared_law or index == refs - 1:
                text = f"{text} {law_text}"
            chunks.append(text)
            gold.update((law_id, *link) for link in links)
        connectors = [", ", ", а также ", " и "] + ([] if shared_law else ["; "])
        connector = self.r.choice(connectors) if refs > 1 else ""
        body = connector.join(chunks) if refs <= 2 else ", ".join(chunks[:-1]) + " и " + chunks[-1]
        return f"{intro} {body} {self.r.choice(FILLERS)}.", gold

    def text(self, sentences: int, refs_range, pool, case_mode, max_list, noise: float, hard: bool = False):
        parts: list[str] = []
        gold: set[Link] = set()
        for _ in range(sentences):
            if self.r.random() < noise:
                parts.append(self.r.choice(NOISE))
            sentence, links = self.sentence(self.r.randint(*refs_range), pool, case_mode, max_list, hard)
            parts.append(sentence)
            gold |= links
        return " ".join(parts), gold


def _readme_case() -> tuple[str, set[Link]]:
    import re

    readme = (ROOT.parent / "homework_task" / "README.md")
    if not readme.exists():
        return "", set()
    text = re.search(r'test_text = """(.*?)"""', readme.read_text(encoding="utf-8"), re.S).group(1)
    gold = {
        (15, "374", "1", "1"), (13, "105", None, None), (0, None, "10", None), (13, "105", "5", None),
        (13, "158", "3", None), (5, "30", None, None), (13, "159", "4", "12"), (13, "228", "2", None),
        (15, "275", None, None), (8, "90", None, None), (10, "70", None, None), (6, "213", "1", None),
        (0, "20", "а", None), (984, "16", None, None), (330, "14", "2", None), (224, "19", None, None),
        (412, "9", "р", None), (284, "16", "1", None), (362, "22", "б", "2"), (332, "12", None, None),
        (249, "20", "3", None), (5, "34", "1", None), (17, "30.1", "3", None), (0, "211", None, None),
    }
    gold |= {(174, "14", "1", value) for value in ("4", "5", "6", "8")}
    gold |= {(15, "66", point, sub) for point in ("3.345", "23") for sub in ("а", "б", "с")}
    return text, gold


def build_levels(seed: int = 2025) -> dict[str, list[tuple[str, set[Link]]]]:
    b = Builder(seed)
    full_pool = {**LAWS_SHORT, **LAWS_FULL}
    levels: dict[str, list[tuple[str, set[Link]]]] = {}
    levels["1_simple"] = [b.text(1, (1, 1), LAWS_SHORT, "abbr", 1, 0.0) for _ in range(CASES_PER_LEVEL)]
    levels["2_full_forms"] = [b.text(b.r.randint(1, 2), (1, 1), full_pool, "mixed", 3, 0.2) for _ in range(CASES_PER_LEVEL)]
    levels["3_chains"] = [b.text(b.r.randint(2, 6), (1, 3), full_pool, "mixed", 3, 0.4) for _ in range(CASES_PER_LEVEL - 1)]
    levels["3_chains"].append(_readme_case())
    levels["4_hard"] = [b.text(b.r.randint(1, 4), (1, 3), {**LAWS_SHORT, **LAWS_HARD}, "mixed", 3, 0.3, hard=True)
                        for _ in range(CASES_PER_LEVEL)]
    return levels


def _http_detector(url: str):
    def detect(text: str) -> set[Link]:
        request = urllib.request.Request(
            url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return {
            (item["law_id"], item["article"], item["point_article"], item["subpoint_article"])
            for item in payload["links"]
        }
    return detect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="evaluate a running service instead of the in-process detector")
    parser.add_argument("--errors", type=int, default=0, help="print up to N failed texts per level")
    parser.add_argument("--seed", type=int, default=2025)
    args = parser.parse_args()

    started = time.perf_counter()
    if args.url:
        detect = _http_detector(args.url)
    else:
        from detector import LawReferenceDetector

        detector = LawReferenceDetector(ROOT / "law_aliases.json")
        detect = lambda text: {item.key for item in detector.detect(text)}  # noqa: E731
    print(f"startup_seconds={time.perf_counter() - started:.2f}")

    levels = build_levels(args.seed)
    total_tp = total_fp = total_fn = 0
    total_elapsed = 0.0
    for name, cases in levels.items():
        tp = fp = fn = 0
        shown = 0
        level_started = time.perf_counter()
        for text, gold in cases:
            actual = detect(text)
            tp += len(actual & gold)
            fp += len(actual - gold)
            fn += len(gold - actual)
            if shown < args.errors and actual != gold:
                shown += 1
                print(f"\n[{name}] {text}\n  missing: {sorted(gold - actual, key=str)}\n  extra:   {sorted(actual - gold, key=str)}")
        elapsed = time.perf_counter() - level_started
        total_elapsed += elapsed
        total_tp, total_fp, total_fn = total_tp + tp, total_fp + fp, total_fn + fn
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        print(f"{name:14s} texts={len(cases)} P={precision:.3f} R={recall:.3f} F1={f1:.3f} time={elapsed:.2f}s")
    precision = total_tp / max(1, total_tp + total_fp)
    recall = total_tp / max(1, total_tp + total_fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    print(f"{'TOTAL':14s} texts={sum(map(len, levels.values()))} P={precision:.3f} R={recall:.3f} F1={f1:.3f} time={total_elapsed:.2f}s")


if __name__ == "__main__":
    main()
