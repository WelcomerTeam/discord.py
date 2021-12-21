import types
from typing import Any, Dict, Mapping, Optional

import sandwich
from sandwich.ext.commands.bot import Bot, BotBase
from sandwich.ext.sandwich.abc import SandwichEvent, SandwichPayload

from .channel import Channel
from .connection import ConnectionMixin


class SandwichBase():
    def __init__(self, **options):
        self.__bots: Dict[str, BotBase] = {}
        self._connection: ConnectionMixin = options.get('connection')
        self._channel: Channel = options.get('channel')

    # internal helpers

    def dispatch(self, payload: SandwichEvent) -> None:
        bot: Bot = self.__bots.get(payload.producer_identifier)
        if bot:
            event_name = payload.event_name
            data = payload.data

            bot._connection.user = sandwich.ClientUser(
                state=bot._connection, data={"id": payload.application_id, "username": "", "discriminator": "", "avatar": ""})
            bot.ws.handle_dispatch(event_name, data)

    # bots

    def add_bot(self, bot_name: str, bot: BotBase, *, override: bool = False) -> None:
        """Adds a "bot" to the Sandwich Consumer.

        A bot is a class that has its own event listeners and commands.
        """

        if not isinstance(bot, BotBase):
            raise TypeError('bots must derive from BotBase')

        existing = self.__bots.get(bot_name)

        if existing is not None:
            if not override:
                raise sandwich.ClientException(
                    f'Cog named {bot_name!r} already loaded')
            self.remove_bot(bot_name)

        self.__bots[bot_name] = bot

    def get_bot(self, identifier: str) -> Optional[BotBase]:
        """Gets the bot instance requested.

        If the bot is not found, None is returned instead.
        """
        return self.__bots.get(identifier)

    def remove_bot(self, identifier: str) -> Optional[BotBase]:
        """Removes a bot from the sandwich consumer and returns it.

        If no bot is found then this method has no effect.
        """

        bot = self.__bots.pop(identifier, None)
        if bot is None:
            return

        return bot

    @property
    def bots(self) -> Mapping[str, BotBase]:
        """Mapping[:class:`str`, :class:`BotBase`]: A read-only mapping of bot identifier to bot."""
        return types.MappingProxyType(self.__bots)
