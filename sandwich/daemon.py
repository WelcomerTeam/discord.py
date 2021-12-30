"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present WelcomerTeam

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from .user import ClientUser, User


class SandwichMetadataPayload(TypedDict):
    v: str
    i: str
    a: str
    id: int
    s: list[int, int, int]


class SandwichPayload(TypedDict):
    op: int
    d: Any
    s: int
    t: str
    __extra: Any
    __sandwich: SandwichMetadataPayload
    __sandwich_trace: dict[str, int]


class SandwichIdentifiersPayload(TypedDict):
    v: str
    identifiers: list[SandwichIdentifierPayload]


class SandwichIdentifierPayload(TypedDict):
    token: str
    id: int
    user: User


class SandwichIdentifiers():
    __slots__ = (
        'v',
        'identifiers',
    )

    def __init__(self, payload: SandwichIdentifiersPayload):
        self.v: str = payload.get('v')
        self.identifiers: dict[str, SandwichIdentifier] = {i: SandwichIdentifier(
            k) for i, k in payload.get('identifiers', {}).items()}

    @property
    def version(self) -> str:
        return self.v

    def get_identifier(self, identifier: str) -> SandwichIdentifier:
        return self.identifiers.get(identifier)


class SandwichIdentifier():
    __slots__ = (
        'token',
        'id',
        'user',
    )

    def __init__(self, payload: SandwichIdentifierPayload):
        self.token: str = payload.get('token')
        self.id: int = payload.get('id')
        self.user: ClientUser = ClientUser(
            state=None, data=payload.get('user'))


class SandwichEvent:
    __slots__ = ('op', 'data', 'sequence', 'type', 'extra',
                 'metadata', 'trace')

    def __init__(self, payload: SandwichPayload):
        self.op: int = payload.get('op')
        self.data: Any = payload.get('d')
        self.type: str = payload.get('t')

        self.sequence: int = payload.get('s', None)
        self.extra: Any = payload.get('__extra', None)
        self.metadata: SandwichMetadataPayload = payload.get('__sandwich', {})
        self.trace: dict[str, int] = payload.get('__sandwich_trace', None)

    @ property
    def event_name(self) -> str:
        return self.type

    @ property
    def version(self) -> str:
        return self.metadata.get('v')

    @ property
    def producer_identifier(self) -> str:
        return self.metadata.get('i')

    @ property
    def application_name(self) -> str:
        return self.metadata.get('a')

    @ property
    def application_id(self) -> int:
        return self.metadata.get('id')

    @ property
    def shard_group_id(self) -> int:
        return self.metadata.get('s', ())[0]

    @ property
    def shard_id(self) -> int:
        return self.metadata.get('s', ())[1]

    @ property
    def shard_count(self) -> int:
        return self.metadata.get('s', ())[2]
