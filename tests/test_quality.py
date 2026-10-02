import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from quality import normalize, validate, write, read
import build


class QualityTests(unittest.TestCase):
    def test_published_bank(self):
        result = validate(ROOT)
        self.assertEqual(result["questions"], 1508)
        self.assertEqual(result["uniqueQuestions"], 1387)

    def fixture(self, root):
        (root / "data").mkdir()
        q = dict(id="one", q="问题", ctx="", a="答案", src="source", type="简答")
        write(root / "data/ch1.json", dict(no=1, title="标题", questions=[q, dict(q, id="two"), dict(q, id="three", a="不同答案")], notes=[]))
        write(root / "data/index.json", dict(chapters=[dict(no=1)], exams=[]))

    def test_merge_only_identical_answers_and_preserve_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp); self.fixture(root)
            report = normalize(root)
            data = read(root / "data/ch1.json")
            self.assertEqual(len(data["questions"]), 3)
            self.assertEqual(data["questions"][0]["canonicalId"], data["questions"][1]["canonicalId"])
            self.assertNotEqual(data["questions"][0]["canonicalId"], data["questions"][2]["canonicalId"])
            self.assertFalse(report[0]["merged"])
            self.assertEqual(validate(root)["uniqueQuestions"], 2)

    def test_reject_empty_question_duplicate_id_and_missing_image(self):
        for change in [lambda qs: qs[0].update(q=""), lambda qs: qs[1].update(id="one"), lambda qs: qs[0].update(answerPages=["pages/missing.jpg"])]:
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp); self.fixture(root); normalize(root)
                path = root / "data/ch1.json"; data = read(path); change(data["questions"]); write(path, data)
                with self.assertRaises(AssertionError): validate(root)

    def test_normalize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp); self.fixture(root); normalize(root)
            before = (root / "data/ch1.json").read_bytes(); version = read(root / "data/index.json")["version"]
            normalize(root)
            self.assertEqual(before, (root / "data/ch1.json").read_bytes())
            self.assertEqual(version, read(root / "data/index.json")["version"])

    def test_failed_validation_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "site"; root.mkdir(); self.fixture(root)
            (root / "pages").mkdir()
            original = (root / "data/ch1.json").read_bytes()
            with patch.object(build, "ROOT", root), patch.object(sys, "argv", ["build.py"]), patch.object(build, "validate", side_effect=ValueError("invalid data")):
                with self.assertRaises(ValueError): build.main()
            self.assertEqual(original, (root / "data/ch1.json").read_bytes())

    def test_promotion_failure_rolls_back_both_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "site"; root.mkdir(); self.fixture(root)
            (root / "pages").mkdir(); (root / "pages/marker").write_text("original")
            original = (root / "data/ch1.json").read_bytes()
            rename = pathlib.Path.rename

            def fail_data_promotion(path, target):
                if path.name == "data" and path.parent != root and pathlib.Path(target) == root / "data":
                    raise OSError("simulated filesystem failure")
                return rename(path, target)

            with patch.object(build, "ROOT", root), patch.object(sys, "argv", ["build.py"]), patch.object(pathlib.Path, "rename", fail_data_promotion):
                with self.assertRaises(OSError): build.main()
            self.assertEqual(original, (root / "data/ch1.json").read_bytes())
            self.assertEqual((root / "pages/marker").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
