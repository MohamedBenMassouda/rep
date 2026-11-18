import unittest

from rep.ai import model_configured, model_object, model_request, model_text
from tests.helpers import model_json, model_response

SETTINGS = {"url": "https://models.example/v1/", "model": "some-model", "key_file": "/nonexistent"}
SCHEMA = {"type": "object"}
OVERLOADED = [{"error": {"code": 503, "status": "UNAVAILABLE"}}]


class ModelTests(unittest.TestCase):
    def test_a_request_goes_to_the_chat_completions_route_of_any_compatible_provider(self):
        request = model_request(SETTINGS, "be brief", "hello")

        self.assertEqual(request["url"], "https://models.example/v1/chat/completions")
        self.assertEqual(request["body"]["model"], "some-model")
        self.assertEqual([message["role"] for message in request["body"]["messages"]], ["system", "user"])
        self.assertNotIn("response_format", request["body"])

    def test_a_schema_asks_for_a_strict_JSON_answer(self):
        request = model_request(SETTINGS, "be brief", "hello", SCHEMA)

        self.assertEqual(request["body"]["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_the_answer_text_is_read_and_an_error_answer_reads_as_nothing(self):
        self.assertEqual(model_text(model_response("  fine  ")), "fine")
        self.assertIsNone(model_text(OVERLOADED))
        self.assertIsNone(model_text(None))
        self.assertIsNone(model_text(model_response("   ")))

    def test_a_JSON_answer_is_read_and_anything_else_reads_as_nothing(self):
        self.assertEqual(model_object(model_json({"answer": "done"})), {"answer": "done"})
        self.assertIsNone(model_object(model_response("not JSON")))
        self.assertIsNone(model_object(model_json(["a", "list"])))

    def test_a_model_without_url_or_name_is_not_configured(self):
        self.assertTrue(model_configured(SETTINGS))
        self.assertFalse(model_configured({**SETTINGS, "model": ""}))


if __name__ == "__main__":
    unittest.main()
