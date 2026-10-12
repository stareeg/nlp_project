from __future__ import annotations

from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector import LawReferenceDetector


CASES_PER_LEVEL = 500
LAWS = [(15, "НК РФ"), (13, "УК РФ"), (0, "АПК РФ"), (17, "КоАП РФ")]


def build_cases(seed: int = 2025) -> list[tuple[str, set[tuple]]]:
    randomizer = random.Random(seed)
    cases: list[tuple[str, set[tuple]]] = []
    for index in range(CASES_PER_LEVEL):
        law_id, alias = LAWS[index % len(LAWS)]
        article = str(1 + index % 400)
        cases.append((f"Согласно ст. {article} {alias}, действует правило.", {(law_id, article, None, None)}))

    for index in range(CASES_PER_LEVEL):
        law_id, alias = randomizer.choice(LAWS)
        article = f"{1 + index % 50}.{1 + index % 9}"
        point = str(1 + index % 12)
        cases.append((f"В пункте {point} статьи {article} {alias} установлено требование.", {(law_id, article, point, None)}))

    for index in range(CASES_PER_LEVEL):
        law_id, alias = randomizer.choice(LAWS)
        article = str(1 + index % 200)
        point = str(1 + index % 10)
        expected = {(law_id, article, point, value) for value in ("а", "б", "в")}
        cases.append((f"В подпунктах а, б и в пункта {point} статьи {article} {alias} есть условия.", expected))

    noise = ["05.02.2025", "12,5 процента", "№ 123-ФЗ", "три приложения"]
    for index in range(CASES_PER_LEVEL):
        law_id, alias = randomizer.choice(LAWS)
        article = str(1 + index % 300)
        point = str(1 + index % 15)
        prefix = randomizer.choice(noise)
        text = f"Документ содержит {prefix}; однако по пунта {point} статьи {article} {alias} действует норма."
        cases.append((text, {(law_id, article, point, None)}))
    return cases


def main() -> None:
    started = time.perf_counter()
    detector = LawReferenceDetector(ROOT / "law_aliases.json")
    startup = time.perf_counter() - started
    cases = build_cases()
    true_positive = false_positive = false_negative = 0
    run_started = time.perf_counter()
    for text, expected in cases:
        actual = {item.key for item in detector.detect(text)}
        true_positive += len(actual & expected)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
    elapsed = time.perf_counter() - run_started
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    print(f"startup_seconds={startup:.3f}")
    print(f"cases={len(cases)} elapsed_seconds={elapsed:.3f} cases_per_second={len(cases) / elapsed:.1f}")
    print(f"precision={precision:.4f} recall={recall:.4f} f1={f1:.4f}")


if __name__ == "__main__":
    main()
