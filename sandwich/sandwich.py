import types
from typing import Dict, Mapping, Optional

from sandwich.ext.sandwich.channel import Channel
from sandwich.ext.sandwich.connection import ConnectionMixin
from sandwich.protobuf.events_pb2 import FetchConsumerConfigurationRequest, FetchConsumerConfigurationResponse

from .errors import ClientException

from .bot import Bot, BotBase
from .daemon import SandwichEvent, SandwichIdentifiers
from .utils import _from_json


class SandwichBase():
    def __init__(self, **options):
        self.__bots: Dict[str, Bot] = {}
        self._identifiers: SandwichIdentifiers = None

        self._connection: ConnectionMixin = options.get('connection', None)
        self._channel: Channel = options.get('channel', None)

    # internal helpers

    async def dispatch(self, event: SandwichEvent) -> None:
        if event.type.startswith("SW_"):
            await self._dispatch(event)

        bot: Bot = self.__bots.get(event.producer_identifier)
        if bot:
            bot.handle_dispatch(event)

    async def _dispatch(self, event: SandwichEvent) -> None:
        if event.type == "SW_CONFIGURATION_RELOAD":
            await self.fetch_identifiers()

        if event.type == "SW_SHARD_STATUS_UPDATE":
            pass

        if event.type == "SW_SHARD_GROUP_STATUS_UPDATE":
            pass

    async def fetch_identifiers(self) -> SandwichIdentifiers:
        result: FetchConsumerConfigurationResponse = await self._channel.stub.FetchConsumerConfiguration(
            FetchConsumerConfigurationRequest())

        self._set_identifiers(SandwichIdentifiers(_from_json(result.file)))

    def _set_identifiers(self, identifiers: SandwichIdentifiers) -> None:
        self._identifiers = identifiers

        for bot in self.__bots.values():
            bot._identifiers = self._identifiers

    # bots

    def add_bot(self, bot_name: str, bot: Bot, *, override: bool = False) -> None:
        """Adds a "bot" to the Sandwich Consumer.

        A bot is a class that has its own event listeners and commands.
        """

        existing = self.__bots.get(bot_name)

        if existing is not None:
            if not override:
                raise ClientException(
                    f'Cog named {bot_name!r} already loaded')
            self.remove_bot(bot_name)

        self.__bots[bot_name] = bot

    def get_bot(self, identifier: str) -> Optional[Bot]:
        """Gets the bot instance requested.

        If the bot is not found, None is returned instead.
        """
        return self.__bots.get(identifier)

    def remove_bot(self, identifier: str) -> Optional[Bot]:
        """Removes a bot from the sandwich consumer and returns it.

        If no bot is found then this method has no effect.
        """

        bot = self.__bots.pop(identifier, None)
        if bot is None:
            return

        return bot

    @property
    def bots(self) -> Mapping[str, Bot]:
        """Mapping[:class:`str`, :class:`Bot`]: A read-only mapping of bot identifier to bot."""
        return types.MappingProxyType(self.__bots)
