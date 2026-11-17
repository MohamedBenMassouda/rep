const BRAIN_NAME = "owner";
const DESKTOP_ROUTE_PREFIX = "/desktop/";
const TELEGRAM_ROUTE = "/telegram";
const TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token";
const TELEGRAM_RECEIVED = "ok";
const AUTHORIZATION_HEADER = "Authorization";
const BEARER_PREFIX = "Bearer ";
const METHOD_POST = "POST";
const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_FOUND = 404;
const EMPTY_BODY = "";
const JSON_HEADERS = { "Content-Type": "application/json" };
const SECRET_DIGEST = "SHA-256";

async function digestOf(text) {
  return crypto.subtle.digest(SECRET_DIGEST, new TextEncoder().encode(text));
}

async function sameSecret(given, expected) {
  if (!given || !expected) {
    return false;
  }

  const [givenDigest, expectedDigest] = await Promise.all([digestOf(given), digestOf(expected)]);

  return crypto.subtle.timingSafeEqual(givenDigest, expectedDigest);
}

function brainOf(env) {
  return env.BRAIN.getByName(BRAIN_NAME);
}

function bearerToken(request) {
  const header = request.headers.get(AUTHORIZATION_HEADER) || EMPTY_BODY;

  return header.startsWith(BEARER_PREFIX) ? header.slice(BEARER_PREFIX.length) : EMPTY_BODY;
}

async function telegramUpdate(request, env, context) {
  if (!(await sameSecret(request.headers.get(TELEGRAM_SECRET_HEADER), env.TELEGRAM_WEBHOOK_SECRET))) {
    return new Response(EMPTY_BODY, { status: HTTP_UNAUTHORIZED });
  }

  context.waitUntil(brainOf(env).telegram(await request.text()));

  return new Response(TELEGRAM_RECEIVED);
}

export default {
  async fetch(request, env, context) {
    const path = new URL(request.url).pathname;

    if (request.method === METHOD_POST && path === TELEGRAM_ROUTE) {
      return telegramUpdate(request, env, context);
    }

    if (request.method !== METHOD_POST || !path.startsWith(DESKTOP_ROUTE_PREFIX)) {
      return new Response(EMPTY_BODY, { status: HTTP_NOT_FOUND });
    }

    if (!(await sameSecret(bearerToken(request), env.DESKTOP_TOKEN))) {
      return new Response(EMPTY_BODY, { status: HTTP_UNAUTHORIZED });
    }

    const action = path.slice(DESKTOP_ROUTE_PREFIX.length);
    const answer = await brainOf(env).desktop(action, await request.text());

    return new Response(answer, { headers: JSON_HEADERS });
  },

  async scheduled(controller, env, context) {
    context.waitUntil(brainOf(env).tick());
  },
};
