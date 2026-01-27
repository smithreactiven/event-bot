# -*- coding: utf-8 -*-
import re
import typing

FULL_NAME_MIN_LEN = 2
FULL_NAME_MAX_LEN = 200
SOCIAL_MAX_LEN = 512

# Instagram: @username, username (буквы, цифры, точки, _), или URL
_RE_INSTAGRAM = re.compile(
    r"^(https?://)?(www\.)?instagram\.com/[\w.]+$|^@?[\w.]{1,}$",
    re.IGNORECASE
)
# Telegram: @username (5-32), t.me/username
_RE_TELEGRAM = re.compile(
    r"^(https?://)?(www\.)?t\.me/[\w]{5,}$|^@?[\w]{5,32}$",
    re.IGNORECASE
)
# VK: vk.com/id123, vk.com/shortname, или короткое имя
_RE_VK = re.compile(
    r"^(https?://)?(www\.)?vk\.com/(id\d+|[\w.]+)$|^[\w.]{2,}$",
    re.IGNORECASE
)


def _clean(s: typing.Optional[str]) -> str:
    return (s or "").strip()


def validate_full_name(text: typing.Optional[str]) -> typing.Tuple[bool, typing.Optional[str]]:
    """(ok, error_message)"""
    s = _clean(text)
    if not s:
        return False, "Введите имя и фамилию."
    if len(s) < FULL_NAME_MIN_LEN:
        return False, "Имя и фамилия слишком короткие."
    if len(s) > FULL_NAME_MAX_LEN:
        return False, "Слишком длинное имя. Максимум {} символов.".format(FULL_NAME_MAX_LEN)
    words = [w for w in s.split() if w]
    if len(words) < 2:
        return False, "Введите имя и фамилию (минимум два слова)."
    if s.isdigit():
        return False, "Имя не может состоять только из цифр."
    forbid = set("<>\"'\\\n\r\t;")
    if any(c in forbid for c in s):
        return False, "Используйте только буквы, пробелы и допустимые символы."
    return True, None


def _validate_social(
    text: typing.Optional[str],
    pattern: re.Pattern,
    kind: str,
    examples: str,
) -> typing.Tuple[bool, typing.Optional[str], typing.Optional[str]]:
    """(ok, error_message, value_to_store_or_None)"""
    s = _clean(text)
    if not s:
        return True, None, None
    if len(s) > SOCIAL_MAX_LEN:
        return False, "Слишком длинная ссылка. Максимум {} символов.".format(SOCIAL_MAX_LEN), None
    if any(c in s for c in "<>\n\r"):
        return False, "Недопустимые символы в ссылке.", None
    if not pattern.match(s):
        return False, "Неверный формат {}. Примеры: {}.".format(kind, examples), None
    return True, None, s


def validate_instagram(text: typing.Optional[str]) -> typing.Tuple[bool, typing.Optional[str], typing.Optional[str]]:
    return _validate_social(
        text,
        _RE_INSTAGRAM,
        "Instagram",
        "@username, instagram.com/username",
    )


def validate_telegram(text: typing.Optional[str]) -> typing.Tuple[bool, typing.Optional[str], typing.Optional[str]]:
    return _validate_social(
        text,
        _RE_TELEGRAM,
        "Telegram",
        "@username, t.me/username",
    )


def validate_vk(text: typing.Optional[str]) -> typing.Tuple[bool, typing.Optional[str], typing.Optional[str]]:
    return _validate_social(
        text,
        _RE_VK,
        "ВКонтакте",
        "vk.com/username, vk.com/id123",
    )
