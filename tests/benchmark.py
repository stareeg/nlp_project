# Свой бенчмарк с разметкой: 4 уровня по 250 текстов, от простых ссылок к сложным.
#   python tests/benchmark.py
#   python tests/benchmark.py --url http://localhost:8978/detect   (проверить запущенный сервис)
#   python tests/benchmark.py --errors 10                          (показать ошибки)
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

TEXTS_PER_LEVEL = 250

CODES_SHORT = {
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
LAWS_HARD = {
    8: ["СК РФ", "Семейного кодекса РФ"],
    17: ["КоАП", "КоАП РФ"],
    330: ["Федерального закона от 27.07.2006 N 152-ФЗ", "Федерального закона от 27.07.2006 № 152-ФЗ «О персональных данных»",
          "Закона № 152-ФЗ", "ФЗ-152", "закона N 152-ФЗ"],
    13: ["УК РФ", "УКРФ", "Уголовного кодекса"],
    15: ["НК РФ", "Налогвого кодекса РФ", "Налогового кодекса"],
    5: ["ГК РФ", "Гражданского кодекса Росийской Федерации"],
}

# падеж первого слова ссылки зависит от предлога
INTROS = [
    ("Согласно", "dat"),
    ("В соответствии с", "ins"),
    ("В силу", "gen"),
    ("На основании", "gen"),
    ("Как указано в", "pre"),
    ("Исходя из", "gen"),
]
WORDS = {
    "article": {"sg": {"gen": "статьи", "dat": "статье", "ins": "статьей", "pre": "статье"},
                "pl": {"gen": "статей", "dat": "статьям", "ins": "статьями", "pre": "статьях"}},
    "point": {"sg": {"gen": "пункта", "dat": "пункту", "ins": "пунктом", "pre": "пункте"},
              "pl": {"gen": "пунктов", "dat": "пунктам", "ins": "пунктами", "pre": "пунктах"}},
    "part": {"sg": {"gen": "части", "dat": "части", "ins": "частью", "pre": "части"},
             "pl": {"gen": "частей", "dat": "частям", "ins": "частями", "pre": "частях"}},
    "subpoint": {"sg": {"gen": "подпункта", "dat": "подпункту", "ins": "подпунктом", "pre": "подпункте"},
                 "pl": {"gen": "подпунктов", "dat": "подпунктам", "ins": "подпунктами", "pre": "подпунктах"}},
}
SHORT = {"article": "ст.", "point": "п.", "part": "ч.", "subpoint": "пп."}
LETTERS = "абвгдежзклмнопрт"
ENDINGS = [
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

# разметка примера из условия задания (tests/example_text.txt)
EXAMPLE_GOLD = {
    (15, "374", "1", "1"), (13, "105", None, None), (0, None, "10", None), (13, "105", "5", None),
    (13, "158", "3", None), (5, "30", None, None), (13, "159", "4", "12"), (13, "228", "2", None),
    (15, "275", None, None), (8, "90", None, None), (10, "70", None, None), (6, "213", "1", None),
    (0, "20", "а", None), (984, "16", None, None), (330, "14", "2", None), (224, "19", None, None),
    (412, "9", "р", None), (284, "16", "1", None), (362, "22", "б", "2"), (332, "12", None, None),
    (249, "20", "3", None), (5, "34", "1", None), (17, "30.1", "3", None), (0, "211", None, None),
    *((174, "14", "1", sub) for sub in ("4", "5", "6", "8")),
    *((15, "66", point, sub) for point in ("3.345", "23") for sub in ("а", "б", "с")),
}


def join(values: list[str]) -> str:
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + " и " + values[-1]


class Generator:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)

    def article(self) -> str:
        if self.r.random() < 0.15:
            return f"{self.r.randint(1, 40)}.{self.r.randint(1, 9)}"
        return str(self.r.randint(1, 450))

    def point(self) -> str:
        return str(self.r.randint(1, 12))

    def subpoint(self) -> str:
        return self.r.choice(LETTERS) if self.r.random() < 0.5 else str(self.r.randint(1, 15))

    def distinct(self, make, count: int) -> list[str]:
        values: list[str] = []
        while len(values) < count:
            value = make()
            if value not in values:
                values.append(value)
        return values

    def typo(self, word: str) -> str:
        # перестановка соседних букв или пропуск буквы
        while True:
            i = self.r.randint(1, len(word) - 3)
            if self.r.random() < 0.5:
                result = word[:i] + word[i + 1] + word[i] + word[i + 2 :]
            else:
                result = word[:i] + word[i + 1 :]
            if result != word:
                return result

    def law(self, pool: dict[int, list[str]]) -> tuple[int, str]:
        law_id = self.r.choice(list(pool))
        return law_id, self.r.choice(pool[law_id])

    def reference(self, case: str | None, max_list: int, hard: bool):
        # одна ссылка в обратном порядке: "пп. 1 п. 2 ст. 3", case=None значит сокращения
        depth = self.r.choice([1, 1, 2, 2, 3])
        middle = "part" if self.r.random() < 0.3 else "point"
        levels = ["article", middle, "subpoint"][:depth]
        listed = self.r.choice(levels) if max_list > 1 and self.r.random() < 0.5 else None
        makers = {"article": self.article, middle: self.point, "subpoint": self.subpoint}
        values = {level: self.distinct(makers[level], self.r.randint(2, max_list) if level == listed else 1)
                  for level in levels}

        parts = []
        for n, level in enumerate(reversed(levels)):
            shown = values[level]
            if hard and level == "subpoint" and shown[0].isalpha() and self.r.random() < 0.6:
                shown = [f"«{value}»" for value in shown]
            plural = len(shown) > 1
            if case is None:
                marker = SHORT[level]
                if hard and level == "subpoint" and self.r.random() < 0.4:
                    marker = "подп."
                if plural and level == "article" and self.r.random() < 0.3:
                    marker = "ст.ст."
            else:
                marker = WORDS[level]["pl" if plural else "sg"][case if n == 0 else "gen"]
                if hard and len(marker) >= 6 and self.r.random() < 0.35:
                    marker = self.typo(marker)
            space = "" if hard and case is None and self.r.random() < 0.3 else " "
            parts.append(f"{marker}{space}{join(shown)}")

        links = [
            (article, point, sub)
            for article in values["article"]
            for point in values.get(middle, [None])
            for sub in values.get("subpoint", [None])
        ]
        return " ".join(parts), links

    def sentence(self, refs: int, pool, case_mode: str, max_list: int, hard: bool):
        intro, case = self.r.choice(INTROS)
        if case_mode == "short" or (case_mode == "mixed" and self.r.random() < 0.5):
            case = None
        gold = set()
        chunks = []
        shared_law = refs > 1 and self.r.random() < 0.3
        law_id, law_text = self.law(pool)
        for n in range(refs):
            text, links = self.reference(case, max_list, hard)
            if not shared_law:
                law_id, law_text = self.law(pool)
            if not shared_law or n == refs - 1:
                text = f"{text} {law_text}"
            chunks.append(text)
            gold.update((law_id, *link) for link in links)
        if refs <= 2:
            body = self.r.choice([", ", ", а также ", " и "] + ([] if shared_law else ["; "])).join(chunks)
        else:
            body = ", ".join(chunks[:-1]) + " и " + chunks[-1]
        return f"{intro} {body} {self.r.choice(ENDINGS)}.", gold

    def back_reference(self):
        # "п. 3 указанной статьи", "ст. 11 того же кодекса", "пункт 2 части 1 статьи 7"
        law_id, law = self.law(CODES_SHORT)
        article, other = self.distinct(self.article, 2)
        point, part = self.point(), self.point()
        ending = self.r.choice(ENDINGS)
        kind = self.r.randint(0, 2)
        if kind == 0:
            return (f"Согласно ст. {article} {law}, при этом п. {point} указанной статьи {ending}.",
                    {(law_id, article, None, None), (law_id, article, point, None)})
        if kind == 1:
            return (f"В ст. {article} {law} и ст. {other} того же кодекса {ending}.",
                    {(law_id, article, None, None), (law_id, other, None, None)})
        return f"Согласно пункту {point} части {part} статьи {article} {law} {ending}.", {(law_id, article, part, point)}

    def text(self, sentences: int, refs, pool, case_mode, max_list, noise: float, hard: bool = False):
        parts = []
        gold = set()
        for _ in range(sentences):
            if self.r.random() < noise:
                parts.append(self.r.choice(NOISE))
            if hard and self.r.random() < 0.2:
                sentence, links = self.back_reference()
            else:
                sentence, links = self.sentence(self.r.randint(*refs), pool, case_mode, max_list, hard)
            parts.append(sentence)
            gold |= links
        return " ".join(parts), gold


def build_levels(seed: int = 2025):
    g = Generator(seed)
    full = {**CODES_SHORT, **LAWS_FULL}
    hard = {**CODES_SHORT, **LAWS_HARD}
    n = TEXTS_PER_LEVEL
    example = ((ROOT / "tests" / "example_text.txt").read_text(encoding="utf-8"), EXAMPLE_GOLD)
    return {
        "1_simple": [g.text(1, (1, 1), CODES_SHORT, "short", 1, 0.0) for _ in range(n)],
        "2_full_forms": [g.text(g.r.randint(1, 2), (1, 1), full, "mixed", 3, 0.2) for _ in range(n)],
        "3_chains": [g.text(g.r.randint(2, 6), (1, 3), full, "mixed", 3, 0.4) for _ in range(n - 1)] + [example],
        "4_hard": [g.text(g.r.randint(1, 4), (1, 3), hard, "mixed", 3, 0.3, hard=True) for _ in range(n)],
    }


def http_detector(url: str):
    def detect(text: str) -> set:
        body = json.dumps({"text": text}).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            links = json.load(response)["links"]
        return {(x["law_id"], x["article"], x["point_article"], x["subpoint_article"]) for x in links}

    return detect


def f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return precision, recall, 2 * precision * recall / max(1e-12, precision + recall)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="адрес запущенного сервиса, например http://localhost:8978/detect")
    parser.add_argument("--errors", type=int, default=0, help="сколько текстов с ошибками показать на уровень")
    parser.add_argument("--seed", type=int, default=2025)
    args = parser.parse_args()

    started = time.perf_counter()
    if args.url:
        detect = http_detector(args.url)
    else:
        from detector import LawReferenceDetector

        detector = LawReferenceDetector(ROOT / "law_aliases.json")

        def detect(text):
            return {link.key for link in detector.detect(text)}

    print(f"startup_seconds={time.perf_counter() - started:.2f}")

    total = [0, 0, 0]
    total_time = 0.0
    levels = build_levels(args.seed)
    for name, cases in levels.items():
        tp = fp = fn = shown = 0
        started = time.perf_counter()
        for text, gold in cases:
            found = detect(text)
            tp += len(found & gold)
            fp += len(found - gold)
            fn += len(gold - found)
            if found != gold and shown < args.errors:
                shown += 1
                print(f"\n[{name}] {text}\n  пропущено: {sorted(gold - found, key=str)}\n  лишнее:    {sorted(found - gold, key=str)}")
        elapsed = time.perf_counter() - started
        total_time += elapsed
        total = [total[0] + tp, total[1] + fp, total[2] + fn]
        p, r, f = f1(tp, fp, fn)
        print(f"{name:14s} texts={len(cases)} P={p:.3f} R={r:.3f} F1={f:.3f} time={elapsed:.2f}s")
    p, r, f = f1(*total)
    count = sum(len(cases) for cases in levels.values())
    print(f"{'TOTAL':14s} texts={count} P={p:.3f} R={r:.3f} F1={f:.3f} time={total_time:.2f}s")


if __name__ == "__main__":
    main()
