from __future__ import annotations

from pathlib import Path
import unittest

from detector import LawReferenceDetector


ROOT = Path(__file__).resolve().parents[1]


def tuples(detector: LawReferenceDetector, text: str):
    return [item.key for item in detector.detect(text)]


class DetectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.detector = LawReferenceDetector(ROOT / "law_aliases.json")

    def test_basic_nested_reference(self):
        self.assertEqual(
            tuples(self.detector, "В соответствии с пп. 1 п. 1 ст. 374 НК РФ применяются правила."),
            [(15, "374", "1", "1")],
        )

    def test_full_names_and_several_laws(self):
        actual = tuples(
            self.detector,
            "Согласно статье 17 Конституции Российской Федерации, действует правило; "
            "по п. 5 ст. 105 УК РФ применяется исключение.",
        )
        self.assertEqual(actual, [(13, "105", "5", None)])

    def test_subpoint_list_is_expanded(self):
        actual = tuples(self.detector, "пп. 1, 2, 3 п. 2 ст. 3 НК РФ")
        self.assertEqual(
            actual,
            [
                (15, "3", "2", "1"),
                (15, "3", "2", "2"),
                (15, "3", "2", "3"),
            ],
        )

    def test_article_list_is_expanded(self):
        actual = tuples(self.detector, "статьи 105, 158 и 159 УК РФ")
        self.assertEqual(
            actual,
            [(13, "105", None, None), (13, "158", None, None), (13, "159", None, None)],
        )

    def test_repeated_groups_do_not_form_cartesian_product(self):
        actual = tuples(self.detector, "п. 1 ст. 10, п. 2 ст. 15 УК РФ")
        self.assertEqual(actual, [(13, "10", "1", None), (13, "15", "2", None)])

    def test_multiple_documents(self):
        actual = tuples(self.detector, "ст. 105 УК РФ и ст. 374 НК РФ")
        self.assertEqual(actual, [(13, "105", None, None), (15, "374", None, None)])

    def test_forward_order(self):
        actual = tuples(self.detector, "НК РФ, статья 374, пункт 2, подпункт 1.")
        self.assertEqual(actual, [(15, "374", "2", "1")])

    def test_part_maps_to_point(self):
        actual = tuples(self.detector, "часть 3, ст. 30.1 КоАП РФ")
        self.assertEqual(actual, [(17, "30.1", "3", None)])

    def test_common_marker_typo(self):
        actual = tuples(self.detector, "подпункту 2 пунта б статьи 22 НК РФ")
        self.assertEqual(actual, [(15, "22", "б", "2")])

    def test_hyphenated_value_is_not_expanded(self):
        actual = tuples(self.detector, "ст. 43.2-6 НК РФ")
        self.assertEqual(actual, [(15, "43.2-6", None, None)])

    def test_unknown_law_and_plain_numbers_are_ignored(self):
        self.assertEqual(tuples(self.detector, "В 2025 году было 12 пунктов и 4 статьи."), [])
        self.assertEqual(tuples(self.detector, "п. 1 ст. 2 случайного кодекса"), [])

    def test_law_without_specific_norm_is_ignored(self):
        self.assertEqual(tuples(self.detector, "НК РФ регулирует налогообложение."), [])

    def test_duplicates_are_removed(self):
        actual = tuples(self.detector, "ст. 10 и статья 10 УК РФ")
        self.assertEqual(actual, [(13, "10", None, None)])

    def test_inflected_full_name(self):
        actual = tuples(self.detector, "В пункте 1 статьи 34 Гражданского кодекса Российской Федерации")
        self.assertEqual(actual, [(5, "34", "1", None)])

    def test_typo_in_law_name_uses_conservative_fallback(self):
        actual = tuples(self.detector, "ст. 34 Граждаснкого кодекса Российской Федерации")
        self.assertEqual(actual, [(5, "34", None, None)])

    def test_fuzzy_fallback_does_not_accept_invented_code(self):
        self.assertEqual(tuples(self.detector, "ст. 34 Случайного кодекса"), [])


if __name__ == "__main__":
    unittest.main()
