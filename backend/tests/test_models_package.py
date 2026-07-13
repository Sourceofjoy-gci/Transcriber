import importlib
import unittest


class ModelsPackageTest(unittest.TestCase):
    def test_domain_models_are_importable(self) -> None:
        module = importlib.import_module("app.models.domain")

        self.assertTrue(hasattr(module, "Organisation"))
        self.assertTrue(hasattr(module, "TranscriptionJob"))


if __name__ == "__main__":
    unittest.main()
