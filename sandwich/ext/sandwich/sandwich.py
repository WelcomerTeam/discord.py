import types
from typing import Dict, Mapping, Optional

import sandwich
from sandwich.bot import Bot, BotBase
from sandwich.abc import SandwichEvent

from .channel import Channel
from .connection import ConnectionMixin


class SandwichBase():
    def __init__(self, **options):
        self.__bots: Dict[str, BotBase] = {}

    # internal helpers

    def dispatch(self, event: SandwichEvent) -> None:
        bot: Bot = self.__bots.get(event.producer_identifier)
        if bot:
            bot.handle_dispatch(event)

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
