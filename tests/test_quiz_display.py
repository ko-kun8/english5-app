import pathlib
import unittest


class QuizDisplayTests(unittest.TestCase):
    def test_quiz_prompt_markup_includes_current_english_word(self) -> None:
        app_path = pathlib.Path(__file__).resolve().parents[1] / "app.py"
        content = app_path.read_text(encoding="utf-8")

        self.assertIn("def build_quiz_prompt_markup", content)
        self.assertIn("current_english", content)
        self.assertIn("hint-box", content)


if __name__ == "__main__":
    unittest.main()
