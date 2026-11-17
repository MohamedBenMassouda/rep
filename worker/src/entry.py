import json

from workers import DurableObject, Response, WorkerEntrypoint

from rep.cloud import Brain, SqlStore

EMPTY_BODY = ""
EMPTY_JSON_OBJECT = "{}"
HTTP_NOT_FOUND = 404


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
        return Brain(self.store)

    async def tick(self):
        return self.brain().tick()["text"]

    async def desktop(self, action, body_text):
        return json.dumps(self.brain().desktop(action, json.loads(body_text or EMPTY_JSON_OBJECT)))


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response(EMPTY_BODY, status=HTTP_NOT_FOUND)
