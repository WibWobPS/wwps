from __future__ import annotations

MAX_PLAYER_NAME = 24
MAX_ID_LENGTH = 64

# The save tables are serialized as rows joined by '*' with fields joined by
# '|', so neither character can appear inside a value.
TABLE_DELIMITERS = "|*"


class InvalidRequestError(Exception):
    pass


def req_int(payload: dict, key: str, default: int = 0,
            minimum: int | None = None, maximum: int | None = None) -> int:
    value = payload.get(key, default)
    if value is None or value == "":
        value = default
    if isinstance(value, bool):
        value = int(value)
    try:
        value = int(value)
    except (TypeError, ValueError) as ex:
        raise InvalidRequestError(f"{key} must be a whole number") from ex
    if minimum is not None and value < minimum:
        raise InvalidRequestError(f"{key} is below the allowed minimum")
    if maximum is not None and value > maximum:
        raise InvalidRequestError(f"{key} is above the allowed maximum")
    return value


def req_str(payload: dict, key: str, default: str = "",
            max_length: int = MAX_ID_LENGTH, required: bool = False) -> str:
    value = payload.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        value = str(value)
    if required and not value:
        raise InvalidRequestError(f"{key} is required")
    if len(value) > max_length:
        raise InvalidRequestError(f"{key} is too long")
    return value


def req_list(payload: dict, key: str, max_length: int = 256) -> list:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidRequestError(f"{key} must be a list")
    if len(value) > max_length:
        raise InvalidRequestError(f"{key} has too many entries")
    return value


def req_dict_list(payload: dict, key: str, max_length: int = 256) -> list[dict]:
    return [entry for entry in req_list(payload, key, max_length)
            if isinstance(entry, dict)]


def clean_name(value: str, max_length: int = MAX_PLAYER_NAME) -> str:
    out = []
    for char in value:
        if char in TABLE_DELIMITERS:
            continue
        if ord(char) < 0x20 or ord(char) == 0x7F:
            continue
        out.append(char)
    return "".join(out).strip()[:max_length]


def is_key_like(value: str, max_length: int = MAX_ID_LENGTH) -> bool:
    if not value or len(value) > max_length:
        return False
    return all(char.isalnum() or char in "-_" for char in value)
