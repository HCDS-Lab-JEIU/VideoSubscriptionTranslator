import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

from codex_models import list_codex_models, normalize_models, select_model


def model(name="model-a", default=True, hidden=False):
    return {"model": name, "displayName": name, "isDefault": default, "hidden": hidden,
            "defaultReasoningEffort": "low", "supportedReasoningEfforts": [
                {"reasoningEffort": "low"}, {"reasoningEffort": "high"}]}


class CodexModelTests(unittest.TestCase):
    def test_catalog_defaults_and_hidden_filter(self):
        models = normalize_models([model(), model("hidden", hidden=True), {"model": "broken"}])
        self.assertEqual(len(models), 1)
        self.assertEqual(select_model(models), ("model-a", "low"))
        self.assertEqual(select_model(models, "model-a", "high"), ("model-a", "high"))
        with self.assertRaises(ValueError):
            select_model(models, "unknown")
        with self.assertRaises(ValueError):
            select_model(models, "model-a", "ultra")
        with self.assertRaises(RuntimeError):
            normalize_models([])

    def test_handshake_pagination_and_process_cleanup(self):
        class Input(io.BytesIO):
            def close(self):
                self.saved = self.getvalue()
                super().close()
        process = Mock()
        process.stdin = Input()
        messages = [{"id": 0, "result": {}}, {"method": "notification"},
                    {"id": 1, "result": {"data": [model()], "nextCursor": "next"}},
                    {"id": 2, "result": {"data": [model("model-b", False)], "nextCursor": None}}]
        process.stdout = io.BytesIO(b"".join((json.dumps(m) + "\n").encode() for m in messages))
        process.poll.return_value = None
        with patch("codex_translator.codex_command", return_value=["fake-codex"]), \
             patch("codex_models.subprocess.Popen", return_value=process):
            result = list_codex_models()
        sent = [json.loads(line) for line in process.stdin.saved.splitlines()]
        self.assertEqual([message["method"] for message in sent], ["initialize", "initialized", "model/list", "model/list"])
        self.assertEqual(sent[-1]["params"]["cursor"], "next")
        self.assertEqual(len(result), 2)
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_timeout_kills_server_and_returns_actionable_error(self):
        killed = threading.Event()
        process = Mock()
        process.poll.return_value = None
        process.kill.side_effect = killed.set
        process.stdout.readline.side_effect = lambda: (killed.wait(2), b"")[1]
        with patch("codex_translator.codex_command", return_value=["fake-codex"]), \
             patch("codex_models.subprocess.Popen", return_value=process), \
             self.assertRaisesRegex(RuntimeError, "초과"):
            list_codex_models(timeout=0.01)
        self.assertTrue(killed.is_set())
        process.wait.assert_called_once()
