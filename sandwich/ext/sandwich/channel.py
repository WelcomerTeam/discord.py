from typing import TYPE_CHECKING

import grpc

from sandwich.errors import ClientException
from sandwich.protobuf.events_pb2 import FetchGuildRequest, GuildsResponse, ListenRequest, ListenResponse
from sandwich.protobuf.events_pb2_grpc import SandwichStub

from ._types import FuncT


class Channel(SandwichStub):
    def __init__(self, **options):
        super().__init__(**options)

        self.channel: grpc.Channel = options.get("channel", None)
        self.hook: FuncT = options.get("hook", None)
        self.stub: SandwichStub = None

    def register_hook(self, hook: FuncT):
        """Registers the hook for the GRPC Listener"""
        self.hook = hook

    async def connect(self, **kwargs):
        """Constructs channel and stub"""
        self.stub = SandwichStub(self.channel)

    async def listen(self):
        """Listens to GRPC events and calls hook"""
        if self.channel is None:
            raise ClientException('channel must include channel')
        if self.stub is None:
            raise ClientException('channel must include stub')
        if self.hook is None:
            raise ClientException('channel must include hook')

        received_message: ListenResponse
        async for received_message in self.stub.Listen(ListenRequest()):
            await self.hook(received_message)
