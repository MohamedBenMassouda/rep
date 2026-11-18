AUTHORIZATION_SCHEME = "Bearer "
JSON_CONTENT_TYPE = "application/json"
USER_AGENT = "rep-desktop"
METHOD_POST = "POST"


def bearer_headers(token):
    return {"Authorization": AUTHORIZATION_SCHEME + token, "Content-Type": JSON_CONTENT_TYPE, "User-Agent": USER_AGENT}
