import re
from typing import Tuple
from aiogram import types

TIME_REGEX = re.compile(r"^(\d+)([smhd])$", re.IGNORECASE)

TIME_MULTIPLIERS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

def parse_duration(time_str: str) -> int | None:
    match = TIME_REGEX.match(time_str.strip())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    return amount * TIME_MULTIPLIERS[unit]

def extract_target_and_args(
    message: types.Message,
) -> Tuple[types.User | None, list[str]]:
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        parts = message.text.split()[1:] if message.text else []
        return target, parts

    parts = message.text.split()[1:] if message.text else []
    if not parts:
        return None, []

    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention" and entity.user:
                return entity.user, parts[1:]

    if parts[0].isdigit():
        dummy_user = types.User(id=int(parts[0]), is_bot=False, first_name="User")
        return dummy_user, parts[1:]

    return None, parts