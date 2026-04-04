from __future__ import annotations

from typing import Any, Callable, Coroutine, TypedDict

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ServerMessage(TypedDict, total=False):
    event: str
    message: str
    code: int | str
    error_code: str
    cid: str
    text: str


type MessageListener = Callable[[ServerMessage], Coroutine[Any, Any, None]]
