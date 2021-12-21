
from typing import Any, TypedDict


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
    __extra: any
    __sandwich: SandwichMetadataPayload
    __sandwich_trace: dict[str, int]


class SandwichEvent:
    __slots__ = ('op', 'data', 'sequence', 'type', 'extra',
                 'metadata', 'trace')

    def __init__(self, payload: SandwichPayload):
        self.op: int = payload.get('op')
        self.data: any = payload.get('d')
        self.type: str = payload.get('t')

        self.sequence: int = payload.get('s', None)
        self.extra: any = payload.get('__extra', None)
        self.metadata: SandwichMetadataPayload = payload.get('__sandwich', {})
        self.trace: dict[str, int] = payload.get('__sandwich_trace', None)

    @property
    def event_name(self) -> str:
        return self.type

    @property
    def version(self) -> str:
        return self.metadata.get('v')

    @property
    def producer_identifier(self) -> str:
        return self.metadata.get('i')

    @property
    def application_name(self) -> str:
        return self.metadata.get('a')

    @property
    def application_id(self) -> int:
        return self.metadata.get('id')

    @property
    def shard_group_id(self) -> int:
        return self.metadata.get('s', ())[0]

    @property
    def shard_id(self) -> int:
        return self.metadata.get('s', ())[1]

    @property
    def shard_count(self) -> int:
        return self.metadata.get('s', ())[2]
