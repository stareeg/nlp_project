from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


LAWS = [
    (15, "НК РФ"),
    (13, "УК РФ"),
    (0, "АПК РФ"),
    (17, "КоАП РФ"),
    (5, "Гражданского кодекса Российской Федерации"),
    (10, "Трудового кодекса Российской Федерации"),
]


def generate(count: int, seed: int) -> list[dict]:
    randomizer = random.Random(seed)
    cases: list[dict] = []
    for case_id in range(count):
        law_id, alias = randomizer.choice(LAWS)
        article = str(randomizer.randint(1, 450))
        point = str(randomizer.randint(1, 20))
        variant = case_id % 4
        if variant == 0:
            text = f"Согласно ст. {article} {alias}, применяется общее правило."
            links = [{"law_id": law_id, "article": article, "point_article": None, "subpoint_article": None}]
        elif variant == 1:
            text = f"В пункте {point} статьи {article} {alias} указано исключение."
            links = [{"law_id": law_id, "article": article, "point_article": point, "subpoint_article": None}]
        elif variant == 2:
            text = f"пп. а, б и в п. {point} ст. {article} {alias}"
            links = [
                {"law_id": law_id, "article": article, "point_article": point, "subpoint_article": value}
                for value in ("а", "б", "в")
            ]
        else:
            text = f"Дата 05.02.2025 не относится к ссылке: по пунта {point} статьи {article} {alias}."
            links = [{"law_id": law_id, "article": article, "point_article": point, "subpoint_article": None}]
        cases.append({"id": case_id, "text": text, "links": links})
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic legal-reference cases")
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--output", type=Path, default=Path("generated_cases.jsonl"))
    args = parser.parse_args()
    cases = generate(args.count, args.seed)
    with args.output.open("w", encoding="utf-8") as target:
        for case in cases:
            target.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"generated={len(cases)} output={args.output}")


if __name__ == "__main__":
    main()
