import json

from workers import DurableObject, Response, WorkerEntrypoint, fetch

from rep.cloud import Brain, SqlStore
from rep.notifiers.telegram import method_url, request_body
from rep.web import bearer_headers

SECRET_TELEGRAM_TOKEN = "TELEGRAM_TOKEN"
SECRET_TELEGRAM_CHAT = "TELEGRAM_CHAT_ID"
SECRET_AI_KEY = "AI_KEY"
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
        return Brain(self.store, secret(self.env, SECRET_TELEGRAM_CHAT),
                     can_ask_model=bool(secret(self.env, SECRET_AI_KEY)))

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

    async def ask_model(self, request):
        try:
            response = await fetch(request["url"], method=METHOD_POST,
                                   headers=bearer_headers(secret(self.env, SECRET_AI_KEY)),
                                   body=json.dumps(request["body"]))

            return await response.json()
        except (OSError, ValueError):
            return None

    async def settle(self, brain, outcome):
        await self.deliver(brain, outcome["telegram"])
        call = outcome.get("model")

        if call:
            answered = brain.model_answered(call, await self.ask_model(call["request"]))
            await self.deliver(brain, answered["telegram"])

    async def tick(self):
        brain = self.brain()
        outcome = brain.tick()
        await self.deliver(brain, outcome["telegram"])

        return outcome["text"]

    async def telegram(self, update_text):
        brain = self.brain()
        outcome = brain.telegram(json.loads(update_text or EMPTY_JSON_OBJECT))
        await self.settle(brain, outcome)

        return outcome["text"]

    async def desktop(self, action, body_text):
        brain = self.brain()
        result = brain.desktop(action, json.loads(body_text or EMPTY_JSON_OBJECT))
        await self.deliver(brain, result["telegram"])

        return json.dumps(result["response"])


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response(EMPTY_BODY, status=HTTP_NOT_FOUND)
