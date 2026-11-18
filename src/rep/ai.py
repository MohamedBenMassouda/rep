import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from rep.web import METHOD_POST, bearer_headers

COMPLETIONS_ROUTE = "/chat/completions"
ROLE_SYSTEM = "system"
ROLE_USER = "user"
SCHEMA_RESPONSE = "json_schema"
SCHEMA_NAME = "answer"
MODEL_TIMEOUT_SECONDS = 25
NO_KEY = ""


class ModelMissing(RuntimeError):
    pass


def model_configured(settings):
    return bool(settings["url"] and settings["model"])


def model_request(settings, instructions, question, schema=None):
    body = {"model": settings["model"],
            "messages": [{"role": ROLE_SYSTEM, "content": instructions}, {"role": ROLE_USER, "content": question}]}

    if schema:
        body["response_format"] = {"type": SCHEMA_RESPONSE,
                                   "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema}}

    return {"url": settings["url"].rstrip("/") + COMPLETIONS_ROUTE, "body": body}


def model_text(response):
    try:
        text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None

    return text.strip() if isinstance(text, str) and text.strip() else None


def model_object(response):
    text = model_text(response)

    try:
        answer = json.loads(text) if text else None
    except ValueError:
        return None

    return answer if isinstance(answer, dict) else None


def model_key(settings):
    try:
        return Path(os.path.expanduser(settings["key_file"])).read_text().strip()
    except OSError:
        return NO_KEY


def ask_model(settings, request):
    key = model_key(settings)

    if not model_configured(settings) or not key:
        raise ModelMissing(f"no AI model set up: fill [ai] url and model and put your key in {settings['key_file']}")

    http_request = urllib.request.Request(request["url"], data=json.dumps(request["body"]).encode(), method=METHOD_POST,
                                          headers=bearer_headers(key))

    try:
        with urllib.request.urlopen(http_request, timeout=MODEL_TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
