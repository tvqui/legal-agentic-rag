import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/kaggle_online_cli.py"
spec = importlib.util.spec_from_file_location("kaggle_online_cli", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class KaggleOnlineCliTests(unittest.TestCase):
    def settings(self):
        return {
            "kernel": "owner/stable-kernel",
            "title": "Stable Kernel",
            "dataset_sources": ["owner/artifacts"],
            "machine_shape": "NvidiaTeslaT4",
            "repo_url": "https://example.test/repo.git",
        }

    def test_notebook_and_metadata_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            original = module.ROOT
            module.ROOT = Path(directory)
            try:
                settings = self.settings()
                fingerprint = module.automation_fingerprint(settings, "abc123")
                folder = module.write_kernel_bundle(settings, "abc123", fingerprint)
                metadata = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
                notebook = json.loads((folder / metadata["code_file"]).read_text(encoding="utf-8"))
                source = "".join(notebook["cells"][0]["source"])
                self.assertEqual(metadata["id"], "owner/stable-kernel")
                self.assertTrue(metadata["enable_gpu"])
                self.assertTrue(metadata["enable_internet"])
                self.assertEqual(metadata["machine_shape"], "NvidiaTeslaT4")
                self.assertEqual(metadata["dataset_sources"], ["owner/artifacts"])
                self.assertIn(fingerprint, source)
                self.assertIn("abc123", source)
                self.assertNotIn("VN_LABOR_API_KEY=", source)
            finally:
                module.ROOT = original

    def test_frontend_env_update_preserves_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("VITE_BACKEND_TARGET=https://old.example\nBACKEND_PROXY_TOKEN=secret\n", encoding="utf-8")
            values = module.update_frontend_env(path, "https://new.ngrok-free.dev")
            text = path.read_text(encoding="utf-8")
            self.assertIn("VITE_BACKEND_TARGET=https://new.ngrok-free.dev", text)
            self.assertIn("BACKEND_PROXY_TOKEN=secret", text)
            self.assertEqual(values["BACKEND_PROXY_TOKEN"], "secret")

    def test_url_and_status_parsing(self):
        self.assertEqual(module.extract_url("x\nREMOTE_BACKEND_URL=https://stable.ngrok-free.dev\n"),
                         "https://stable.ngrok-free.dev")
        self.assertEqual(module.parse_status('Kernel has status "RUNNING"'), "running")
        self.assertEqual(module.parse_status('Kernel has status "ERROR"'), "error")


if __name__ == "__main__":
    unittest.main()
