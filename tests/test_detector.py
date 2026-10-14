from pathlib import Path
import unittest

from detector import LawReferenceDetector


ROOT = Path(__file__).resolve().parents[1]


class DetectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = LawReferenceDetector(ROOT / "law_aliases.json")

    def check(self, text, expected):
        self.assertEqual([link.key for link in self.detector.detect(text)], expected, text)

    def test_simple(self):
        self.check("В соответствии с пп. 1 п. 1 ст. 374 НК РФ применяются правила.", [(15, "374", "1", "1")])
        self.check("ст.10 НК РФ", [(15, "10", None, None)])
        self.check("п 2 ст 10 НК РФ", [(15, "10", "2", None)])

    def test_unknown_law_is_skipped(self):
        self.check(
            "Согласно статье 17 Конституции Российской Федерации, действует правило; по п. 5 ст. 105 УК РФ исключение.",
            [(13, "105", "5", None)],
        )
        self.check("п. 1 ст. 2 случайного кодекса", [])
        self.check("ст. 34 Случайного кодекса", [])
        self.check("ст. 1 Конституции РФ", [])

    def test_lists(self):
        self.check("пп. 1, 2, 3 п. 2 ст. 3 НК РФ", [(15, "3", "2", "1"), (15, "3", "2", "2"), (15, "3", "2", "3")])
        self.check("статьи 105, 158 и 159 УК РФ", [(13, "105", None, None), (13, "158", None, None), (13, "159", None, None)])
        self.check("ст. 143 и 332, а также ст. 227 НК РФ", [(15, "143", None, None), (15, "332", None, None), (15, "227", None, None)])

    def test_several_articles_of_one_law(self):
        self.check("п. 1 ст. 10, п. 2 ст. 15 УК РФ", [(13, "10", "1", None), (13, "15", "2", None)])

    def test_several_laws(self):
        self.check("ст. 105 УК РФ и ст. 374 НК РФ", [(13, "105", None, None), (15, "374", None, None)])
        self.check("ст. 105 УК РФ, ч. 2 ст. 158 УК РФ", [(13, "105", None, None), (13, "158", "2", None)])
        self.check("п. 1 ст. 9 КоАП РФ, п. 4 ст. 304 НК РФ", [(17, "9", "1", None), (15, "304", "4", None)])
        self.check(
            "Согласно статье 23 Налогового кодекса и ст. 145 Гражданского кодекса, пп. 1, 2 п. 2 ст. 3 НК РФ",
            [(15, "23", None, None), (5, "145", None, None), (15, "3", "2", "1"), (15, "3", "2", "2")],
        )

    def test_law_before_requisites(self):
        self.check("НК РФ, статья 374, пункт 2, подпункт 1.", [(15, "374", "2", "1")])
        self.check("ГК РФ (ст. 10)", [(5, "10", None, None)])

    def test_part(self):
        self.check("часть 3, ст. 30.1 КоАП РФ", [(17, "30.1", "3", None)])
        self.check("пп. 1 ч. 2 ст. 3 НК РФ", [(15, "3", "2", "1")])
        self.check("пункт 2 части 1 статьи 7 УК РФ", [(13, "7", "1", "2")])

    def test_same_article_and_same_law(self):
        self.check("согласно ст. 10 НК РФ, п. 3 указанной статьи", [(15, "10", None, None), (15, "10", "3", None)])
        self.check("в ст. 10 ГК РФ и ст. 11 того же кодекса", [(5, "10", None, None), (5, "11", None, None)])
        self.check("п. 3 указанной статьи и ст. 5 ГК РФ", [(5, "5", None, None)])
        self.check("в ст. 10 ГК РФ и ст. 11 этого же кодекса", [(5, "10", None, None), (5, "11", None, None)])
        self.check("в ст. 10 ГК РФ, ст. 11 там же", [(5, "10", None, None), (5, "11", None, None)])

    def test_values(self):
        self.check("ст. 43.2-6 НК РФ", [(15, "43.2-6", None, None)])
        self.check("пп. «а» и «е» п. 1 ст. 10 НК РФ", [(15, "10", "1", "а"), (15, "10", "1", "е")])
        self.check("подп. 13 ч. 9 ст. 310 УК РФ", [(13, "310", "9", "13")])
        self.check("пп.л п. 2 ст. 252 ЖК РФ", [(7, "252", "2", "л")])

    def test_ranges(self):
        for text in ("ст. 10-12 УК РФ", "ст. 10 – 12 УК РФ", "статьи с 10 по 12 УК РФ"):
            self.check(text, [(13, "10-12", None, None)])
        self.check("ст. 10; 11 УК РФ", [(13, "10", None, None), (13, "11", None, None)])
        self.check("по ст. 158 - 3 года УК РФ", [(13, "158", None, None)])

    def test_ordinal_parts(self):
        self.check("согласно части первой статьи 5 УК РФ", [(13, "5", "1", None)])
        self.check("ч. первая ст. 5 УК РФ", [(13, "5", "1", None)])
        self.check("ст. 217 части второй НК РФ", [(15, "217", None, None)])

    def test_inflected_names(self):
        self.check("В пункте 1 статьи 34 Гражданского кодекса Российской Федерации", [(5, "34", "1", None)])
        self.check("ст. 1 Закона о полиции", [(249, "1", None, None)])

    def test_typos(self):
        self.check("подпункту 2 пунта б статьи 22 НК РФ", [(15, "22", "б", "2")])
        self.check("в пукнте 2 стаьи 5 УК РФ", [(13, "5", "2", None)])
        self.check("ст. 34 Граждаснкого кодекса Российской Федерации", [(5, "34", None, None)])
        self.check("ст. 431 Налогвого кодекса РФ, ст. 170 УПК РФ", [(15, "431", None, None), (12, "170", None, None)])

    def test_spellings_missing_in_dictionary(self):
        self.check("ст. 90 СК РФ", [(8, "90", None, None)])
        self.check("ч. 3 ст. 30.1 КоАП", [(17, "30.1", "3", None)])
        self.check("ст. 10 УКРФ", [(13, "10", None, None)])
        for text in ("ст. 6 Федерального закона от 27.07.2006 N 152-ФЗ", "ст. 6 закона № 152-ФЗ", "ст. 6 ФЗ-152"):
            self.check(text, [(330, "6", None, None)])

    def test_code_abbreviations(self):
        for text in ("ст. 105 УК-РФ", "ст. 105 У.К. РФ", "ст. 105 У К РФ"):
            self.check(text, [(13, "105", None, None)])
        self.check("ст. 1 ГрК РФ", [(4, "1", None, None)])
        self.check("ст. 1 КАС РФ", [(18, "1", None, None)])
        self.check("ст. 1 ВК РФ", [(2, "1", None, None)])
        self.check("ст. 1 ВзК РФ", [(3, "1", None, None)])
        self.check("ст. 1 ТК ЕАЭС", [(9, "1", None, None)])
        self.check("ст. 81 ТК РФ", [(10, "81", None, None)])
        self.check("Применяется ст. 5, т.к. РФ является стороной договора.", [])

    def test_no_links(self):
        self.check("", [])
        self.check("   ", [])
        self.check("В 2025 году было 12 пунктов и 4 статьи.", [])
        self.check("НК РФ регулирует налогообложение.", [])
        self.check("Статус 5 присвоен, честь 3 раз, в зале № 4.", [])

    def test_duplicates(self):
        self.check("ст. 10 и статья 10 УК РФ", [(13, "10", None, None)])


if __name__ == "__main__":
    unittest.main()
