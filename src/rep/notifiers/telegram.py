import json

API_ROOT = "https://api.telegram.org/bot"
CALLBACK_SEPARATOR = " "
PHONE_COMMANDS = ("answer", "rate", "dismiss", "session")
MESSAGE_LIMIT = 4096
CALLBACK_DATA_LIMIT = 64
SESSION_COMMAND = "session"
BUTTONS_PER_ROW = 2
NO_SESSIONS_TEXT = "No training days yet: add a routine with `rep init` on your desktop."
SESSION_PROMPT = "Which training day did you do?"
METHOD_SEND = "sendMessage"
METHOD_CLEAR_BUTTONS = "editMessageReplyMarkup"
METHOD_ACKNOWLEDGE = "answerCallbackQuery"
TYPE_REPS_HINT = "Send the reps you did as a number first if they differ from {target}, then tap how it felt."


def method_url(token, method):
    return f"{API_ROOT}{token}/{method}"


def callback_data(button):
    return CALLBACK_SEPARATOR.join(button.arguments)


def callback_arguments(data):
    return data.split(CALLBACK_SEPARATOR)


def phone_buttons(card):
    return [button for button in card.buttons if button.arguments and button.arguments[0] in PHONE_COMMANDS]


def card_text(card):
    lines = [card.title, card.body]

    if card.done_prompt is not None:
        lines.append(TYPE_REPS_HINT.format(target=card.done_prompt))

    return "\n".join(line for line in lines if line)


def send_card(chat_id, card):
    payload = {"chat_id": chat_id, "text": card_text(card)}
    buttons = phone_buttons(card)

    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": button.label, "callback_data": callback_data(button)}
                                                        for button in buttons]]}

    return {"method": METHOD_SEND, "payload": payload, "remember": bool(buttons)}


def send_text(chat_id, text):
    return {"method": METHOD_SEND, "payload": {"chat_id": chat_id, "text": text}, "remember": False}


def clear_buttons(chat_id, message_id):
    return {"method": METHOD_CLEAR_BUTTONS, "payload": {"chat_id": chat_id, "message_id": message_id,
                                                        "reply_markup": {"inline_keyboard": []}}, "remember": False}


def acknowledge(callback_query_id, text):
    return {"method": METHOD_ACKNOWLEDGE, "payload": {"callback_query_id": callback_query_id, "text": text},
            "remember": False}


def split_message(text):
    chunks, current = [], ""

    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line

        if len(candidate) > MESSAGE_LIMIT and current:
            chunks.append(current)
            candidate = line

        current = candidate[:MESSAGE_LIMIT]

    return chunks + [current] if current else chunks


def send_long_text(chat_id, text):
    return [send_text(chat_id, chunk) for chunk in split_message(text)]


def session_picker(chat_id, session_names):
    buttons = [{"text": name, "callback_data": f"{SESSION_COMMAND}{CALLBACK_SEPARATOR}{name}"} for name in session_names
               if len(f"{SESSION_COMMAND}{CALLBACK_SEPARATOR}{name}".encode()) <= CALLBACK_DATA_LIMIT]

    if not buttons:
        return send_text(chat_id, NO_SESSIONS_TEXT)

    rows = [buttons[start:start + BUTTONS_PER_ROW] for start in range(0, len(buttons), BUTTONS_PER_ROW)]

    return {"method": METHOD_SEND, "payload": {"chat_id": chat_id, "text": SESSION_PROMPT,
                                               "reply_markup": {"inline_keyboard": rows}}, "remember": False}


def today_text(today):
    trained = ", ".join(today["trained"]) or "nothing logged yet"
    skills = [f"• {skill}: {step}" for skill, step in today["skills"].items()]

    return "\n".join([f"Today: {today['done']} sets · streak {today['streak']} days", f"Trained: {trained}"]
                     + (["", "Skills"] + skills if skills else []))


def routine_text(descriptions):
    return "\n".join(f"• {name}: {muscles}" for name, muscles in descriptions.items()) or NO_SESSIONS_TEXT


def request_body(call):
    return json.dumps(call["payload"])
