import asyncio
from typing import TYPE_CHECKING

from ._types import FuncT
from sandwich.errors import ClientException


class ConnectionMixin():
    def __init__(self, loop: asyncio.AbstractEventLoop = None, **options):
        self.hook: FuncT = options.get("hook", None)
        self.hook_exception: FuncT = options.get("hook_exception", None)
        self.loop = asyncio.get_event_loop() if loop is None else loop

    def register_hook(self, hook: FuncT):
        """Updates the hook for a Connection"""
        self.hook = hook

    def register_hook_exception(self, hook_exception: FuncT):
        """Updates the hook exception for a Connection"""
        self.hook_exception = hook_exception

    async def connect(self, **kwargs):
        """Constructs connection"""
        pass

    async def start(self, **kwargs):
        """Starts listening to the connections channel and send data to hook"""
        if self.hook is None:
            raise ClientException('connection must include hook')
        pass

    async def stop(self):
        """Stops listening to connections channel"""
        pass
