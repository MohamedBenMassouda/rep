import json

API_ROOT = "https://api.telegram.org/bot"
CALLBACK_SEPARATOR = " "
PHONE_COMMANDS = ("answer", "rate", "dismiss")
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


def request_body(call):
    return json.dumps(call["payload"])
