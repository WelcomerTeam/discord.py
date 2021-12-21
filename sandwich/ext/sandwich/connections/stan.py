from sandwich.errors import ClientException
from sandwich.ext.sandwich.connection import ConnectionMixin, FuncT

from nats.aio.client import Client as NATS
from stan.aio.client import Client as STAN


class StanConnection(ConnectionMixin):
    def __init__(self, **options):
        super().__init__(**options)

    def register_hook(self, hook: FuncT):
        return super().register_hook(hook)

    def register_hook_exception(self, hook_exception: FuncT):
        return super().register_hook_exception(hook_exception)

    async def connect(self, cluster_id: str, client_id: str, **kwargs):
        self._nc = NATS()
        self._sc = STAN()

        await self._nc.connect(io_loop=self.loop, **kwargs)
        await self._sc.connect(cluster_id=cluster_id, client_id=client_id, nats=self._nc, **kwargs)

    async def start(self, subject: str, **kwargs):
        if self.hook is None:
            raise ClientException('connection must include hook')
        self._subscription = await self._sc.subscribe(subject=subject, cb=self.hook, error_cb=self.hook_exception)

    async def stop(self):
        await self._subscription.close()
