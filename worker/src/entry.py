import json

from workers import DurableObject, Response, WorkerEntrypoint, fetch

from rep.cloud import Brain, SqlStore
from rep.notifiers.telegram import method_url, request_body

SECRET_TELEGRAM_TOKEN = "TELEGRAM_TOKEN"
SECRET_TELEGRAM_CHAT = "TELEGRAM_CHAT_ID"
NO_SECRET = ""
EMPTY_BODY = ""
EMPTY_JSON_OBJECT = "{}"
METHOD_POST = "POST"
HTTP_NOT_FOUND = 404
JSON_HEADERS = {"Content-Type": "application/json"}


def secret(env, name):
    value = getattr(env, name, None)

    return value if isinstance(value, str) else NO_SECRET


def python_row(row):
    return dict(row) if isinstance(row, dict) else dict(row.to_py())


class RepBrain(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.sql = ctx.storage.sql
        self.store = SqlStore(self.execute)

    def execute(self, statement, *parameters):
        return [python_row(row) for row in self.sql.exec(statement, *parameters).toArray()]

    def brain(self):
        return Brain(self.store, secret(self.env, SECRET_TELEGRAM_CHAT))

    async def deliver(self, brain, calls):
        token = secret(self.env, SECRET_TELEGRAM_TOKEN)

        if not token:
            return

        for call in calls:
            try:
                response = await fetch(method_url(token, call["method"]), method=METHOD_POST, headers=JSON_HEADERS,
                                       body=request_body(call))
                answer = await response.json()
            except (OSError, ValueError):
                continue

            if call["remember"] and answer.get("ok"):
                brain.remember_message(answer["result"]["message_id"])

    async def tick(self):
        brain = self.brain()
        outcome = brain.tick()
        await self.deliver(brain, outcome["telegram"])

        return outcome["text"]

    async def telegram(self, update_text):
        brain = self.brain()
        outcome = brain.telegram(json.loads(update_text or EMPTY_JSON_OBJECT))
        await self.deliver(brain, outcome["telegram"])

        return outcome["text"]

    async def desktop(self, action, body_text):
        brain = self.brain()
        result = brain.desktop(action, json.loads(body_text or EMPTY_JSON_OBJECT))
        await self.deliver(brain, result["telegram"])

        return json.dumps(result["response"])


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response(EMPTY_BODY, status=HTTP_NOT_FOUND)
