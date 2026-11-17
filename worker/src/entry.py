import hmac
import json
from urllib.parse import urlparse

from workers import DurableObject, Response, WorkerEntrypoint

from rep.cloud import Brain, SqlStore

BRAIN_NAME = "owner"
SECRET_DESKTOP_TOKEN = "DESKTOP_TOKEN"
NO_SECRET = ""
EMPTY_BODY = ""
EMPTY_JSON_OBJECT = "{}"
DESKTOP_ROUTE_PREFIX = "/desktop/"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
METHOD_POST = "POST"
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
JSON_HEADERS = {"Content-Type": "application/json"}


def secret(env, name):
    value = getattr(env, name, None)

    return value if isinstance(value, str) else NO_SECRET


def python_row(row):
    return dict(row) if isinstance(row, dict) else dict(row.to_py())


def same_secret(given, expected):
    return bool(expected) and hmac.compare_digest((given or NO_SECRET).encode(), expected.encode())


class RepBrain(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.sql = ctx.storage.sql
        self.store = SqlStore(self.execute)

    def execute(self, statement, *parameters):
        return [python_row(row) for row in self.sql.exec(statement, *parameters).toArray()]

    def brain(self):
        return Brain(self.store)

    async def tick(self):
        return self.brain().tick()["text"]

    async def desktop(self, action, body_text):
        return json.dumps(self.brain().desktop(action, json.loads(body_text or EMPTY_JSON_OBJECT)))


class Default(WorkerEntrypoint):
    def brain_stub(self):
        return self.env.BRAIN.getByName(BRAIN_NAME)

    async def fetch(self, request):
        path = urlparse(request.url).path

        if request.method != METHOD_POST or not path.startswith(DESKTOP_ROUTE_PREFIX):
            return Response(EMPTY_BODY, status=HTTP_NOT_FOUND)

        given = (request.headers.get(AUTHORIZATION_HEADER) or NO_SECRET).removeprefix(BEARER_PREFIX)

        if not same_secret(given, secret(self.env, SECRET_DESKTOP_TOKEN)):
            return Response(EMPTY_BODY, status=HTTP_UNAUTHORIZED)

        answer = await self.brain_stub().desktop(path.removeprefix(DESKTOP_ROUTE_PREFIX), await request.text())

        return Response(answer, headers=JSON_HEADERS)

    async def scheduled(self, controller, env, ctx):
        await self.brain_stub().tick()
