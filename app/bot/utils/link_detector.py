import re

GENERAL_URL_REGEX = re.compile(
    r"https://phonofilm.cc/"
    r"\b[a-zA-Z0-9-]+\.(?:com|org|net|io|xyz|co|me|gg|app|link|site|top|online|tech|shop|biz|info|cc|to)(?:/[^\s]*)?\b"
)

TELEGRAM_INVITE_REGEX = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?(?:t(?:elegram)?\.me|telegram\.dog)/(?:joinchat/|\+)[a-zA-Z0-9_-]+"
)

def contains_telegram_invite(text: str) -> bool:
    return bool(TELEGRAM_INVITE_REGEX.search(text))

def contains_link(text: str) -> bool:
    return bool(GENERAL_URL_REGEX.search(text))