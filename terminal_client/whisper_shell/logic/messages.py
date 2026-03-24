from __future__ import annotations

from typing import Any, Callable, Coroutine, TypeAlias, TypedDict

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ServerMessage(TypedDict, total=False):
    event: str
    message: str
    code: int | str
    error_code: str
    cid: str
    text: str


MessageListener: TypeAlias = Callable[[ServerMessage], Coroutine[Any, Any, None]]
