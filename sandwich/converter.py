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

import inspect
import re
from dataclasses import dataclass, field
from typing import (TYPE_CHECKING, Any, Dict, Generic, Iterable, Iterator,
                    List, Literal, Optional, Pattern, Protocol, Set, Tuple,
                    Type, TypeVar, Union, runtime_checkable)

import sandwich
from sandwich.utils import MISSING, maybe_coroutine, resolve_annotation

from .errors import *
from .errors import (BadFlagArgument, CommandError, MissingFlagArgument,
                     MissingRequiredFlag, TooManyFlags)
from .view import StringView

if TYPE_CHECKING:
    from .context import Context
    from sandwich.message import PartialMessageableChannel

import sys

__all__ = (
    'Converter',
    'ObjectConverter',
    'MemberConverter',
    'UserConverter',
    'MessageConverter',
    'PartialMessageConverter',
    'TextChannelConverter',
    'InviteConverter',
    'GuildConverter',
    'RoleConverter',
    'GameConverter',
    'ColourConverter',
    'ColorConverter',
    'VoiceChannelConverter',
    'StageChannelConverter',
    'EmojiConverter',
    'PartialEmojiConverter',
    'CategoryChannelConverter',
    'IDConverter',
    'StoreChannelConverter',
    'ThreadConverter',
    'GuildChannelConverter',
    'GuildStickerConverter',
    'clean_content',
    'Greedy',
    'run_converters',
    'Flag',
    'flag',
    'FlagConverter',
)


def _get_from_guilds(bot, getter, argument):
    result = None
    for guild in bot.guilds:
        result = getattr(guild, getter)(argument)
        if result:
            return result
    return result


_utils_get = sandwich.utils.get
T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)
CT = TypeVar('CT', bound=sandwich.abc.GuildChannel)
TT = TypeVar('TT', bound=sandwich.Thread)


@runtime_checkable
class Converter(Protocol[T_co]):
    """The base class of custom converters that require the :class:`.Context`
    to be passed to be useful.

    This allows you to implement converters that function similar to the
    special cased ``discord`` classes.

    Classes that derive from this should override the :meth:`~.Converter.convert`
    method to do its conversion logic. This method must be a :ref:`coroutine <coroutine>`.
    """

    async def convert(self, ctx: Context, argument: str) -> T_co:
        """|coro|

        The method to override to do conversion logic.

        If an error is found while converting, it is recommended to
        raise a :exc:`.CommandError` derived exception as it will
        properly propagate to the error handlers.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context that the argument is being used in.
        argument: :class:`str`
            The argument that is being converted.

        Raises
        -------
        :exc:`.CommandError`
            A generic exception occurred when converting the argument.
        :exc:`.BadArgument`
            The converter failed to convert the argument.
        """
        raise NotImplementedError('Derived classes need to implement this.')


_ID_REGEX = re.compile(r'([0-9]{15,20})$')


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument):
        return _ID_REGEX.match(argument)


class ObjectConverter(IDConverter[sandwich.Object]):
    """Converts to a :class:`~sandwich.Object`.

    The argument must follow the valid ID or mention formats (e.g. `<@80088516616269824>`).

    .. versionadded:: 2.0

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by member, role, or channel mention.
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Object:
        match = self._get_id_match(argument) or re.match(
            r'<(?:@(?:!|&)?|#)([0-9]{15,20})>$', argument)

        if match is None:
            raise ObjectNotFound(argument)

        result = int(match.group(1))

        return sandwich.Object(id=result)


class MemberConverter(IDConverter[sandwich.Member]):
    """Converts to a :class:`~sandwich.Member`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name#discrim
    4. Lookup by name
    5. Lookup by nickname

    .. versionchanged:: 1.5
         Raise :exc:`.MemberNotFound` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.5.1
        This converter now lazily fetches members from the gateway and HTTP APIs,
        optionally caching the result if :attr:`.MemberCacheFlags.joined` is enabled.
    """

    async def query_member_named(self, guild, argument):
        cache = guild._state.member_cache_flags.joined
        if len(argument) > 5 and argument[-5] == '#':
            username, _, discriminator = argument.rpartition('#')
            members = await guild.query_members(username, limit=100, cache=cache)
            return sandwich.utils.get(members, name=username, discriminator=discriminator)
        else:
            members = await guild.query_members(argument, limit=100, cache=cache)
            return sandwich.utils.find(lambda m: m.name == argument or m.nick == argument, members)

    async def query_member_by_id(self, bot, guild, user_id):
        raise NotImplementedError()

    async def convert(self, ctx: Context, argument: str) -> sandwich.Member:
        bot = ctx.bot
        match = self._get_id_match(argument) or re.match(
            r'<@!?([0-9]{15,20})>$', argument)
        guild = ctx.guild
        result = None
        user_id = None
        if match is None:
            # not a mention...
            if guild:
                result = guild.get_member_named(argument)
            else:
                result = _get_from_guilds(bot, 'get_member_named', argument)
        else:
            user_id = int(match.group(1))
            if guild:
                result = guild.get_member(user_id) or _utils_get(
                    ctx.message.mentions, id=user_id)
            else:
                result = _get_from_guilds(bot, 'get_member', user_id)

        if result is None:
            if guild is None:
                raise MemberNotFound(argument)

            if user_id is not None:
                result = await self.query_member_by_id(bot, guild, user_id)
            else:
                result = await self.query_member_named(guild, argument)

            if not result:
                raise MemberNotFound(argument)

        return result


class UserConverter(IDConverter[sandwich.User]):
    """Converts to a :class:`~sandwich.User`.

    All lookups are via the global user cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name#discrim
    4. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.UserNotFound` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.6
        This converter now lazily fetches users from the HTTP APIs if an ID is passed
        and it's not available in cache.
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.User:
        match = self._get_id_match(argument) or re.match(
            r'<@!?([0-9]{15,20})>$', argument)
        result = None
        state = ctx._state

        if match is not None:
            user_id = int(match.group(1))
            result = ctx.bot.get_user(user_id) or _utils_get(
                ctx.message.mentions, id=user_id)
            if result is None:
                try:
                    result = await ctx.bot.fetch_user(user_id)
                except sandwich.HTTPException:
                    raise UserNotFound(argument) from None

            return result

        arg = argument

        # Remove the '@' character if this is the first character from the argument
        if arg[0] == '@':
            # Remove first character
            arg = arg[1:]

        # check for discriminator if it exists,
        if len(arg) > 5 and arg[-5] == '#':
            discrim = arg[-4:]
            name = arg[:-5]
            def predicate(
                u): return u.name == name and u.discriminator == discrim
            result = sandwich.utils.find(predicate, state._users.values())
            if result is not None:
                return result

        def predicate(u): return u.name == arg
        result = sandwich.utils.find(predicate, state._users.values())

        if result is None:
            raise UserNotFound(argument)

        return result


class PartialMessageConverter(Converter[sandwich.PartialMessage]):
    """Converts to a :class:`sandwich.PartialMessage`.

    .. versionadded:: 1.7

    The creation strategy is as follows (in order):

    1. By "{channel ID}-{message ID}" (retrieved by shift-clicking on "Copy ID")
    2. By message ID (The message is assumed to be in the context channel.)
    3. By message URL
    """

    @staticmethod
    def _get_id_matches(ctx, argument):
        id_regex = re.compile(
            r'(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})$')
        link_regex = re.compile(
            r'https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/'
            r'(?P<guild_id>[0-9]{15,20}|@me)'
            r'/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$'
        )
        match = id_regex.match(argument) or link_regex.match(argument)
        if not match:
            raise MessageNotFound(argument)
        data = match.groupdict()
        channel_id = sandwich.utils._get_as_snowflake(data, 'channel_id')
        message_id = int(data['message_id'])
        guild_id = data.get('guild_id')
        if guild_id is None:
            guild_id = ctx.guild and ctx.guild.id
        elif guild_id == '@me':
            guild_id = None
        else:
            guild_id = int(guild_id)
        return guild_id, message_id, channel_id

    @staticmethod
    def _resolve_channel(ctx, guild_id, channel_id) -> Optional[PartialMessageableChannel]:
        if guild_id is not None:
            guild = ctx.bot.get_guild(guild_id)
            if guild is not None and channel_id is not None:
                return guild._resolve_channel(channel_id)  # type: ignore
            else:
                return None
        else:
            return ctx.bot.get_channel(channel_id) if channel_id else ctx.channel

    async def convert(self, ctx: Context, argument: str) -> sandwich.PartialMessage:
        guild_id, message_id, channel_id = self._get_id_matches(ctx, argument)
        channel = self._resolve_channel(ctx, guild_id, channel_id)
        if not channel:
            raise ChannelNotFound(channel_id)
        return sandwich.PartialMessage(channel=channel, id=message_id)


class MessageConverter(IDConverter[sandwich.Message]):
    """Converts to a :class:`sandwich.Message`.

    .. versionadded:: 1.1

    The lookup strategy is as follows (in order):

    1. Lookup by "{channel ID}-{message ID}" (retrieved by shift-clicking on "Copy ID")
    2. Lookup by message ID (the message **must** be in the context channel)
    3. Lookup by message URL

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound`, :exc:`.MessageNotFound` or :exc:`.ChannelNotReadable` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Message:
        guild_id, message_id, channel_id = PartialMessageConverter._get_id_matches(
            ctx, argument)
        message = ctx.bot._connection._get_message(message_id)
        if message:
            return message
        channel = PartialMessageConverter._resolve_channel(
            ctx, guild_id, channel_id)
        if not channel:
            raise ChannelNotFound(channel_id)
        try:
            return await channel.fetch_message(message_id)
        except sandwich.NotFound:
            raise MessageNotFound(argument)
        except sandwich.Forbidden:
            raise ChannelNotReadable(channel)


class GuildChannelConverter(IDConverter[sandwich.abc.GuildChannel]):
    """Converts to a :class:`~sandwich.abc.GuildChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name.

    .. versionadded:: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.abc.GuildChannel:
        return self._resolve_channel(ctx, argument, 'channels', sandwich.abc.GuildChannel)

    @staticmethod
    def _resolve_channel(ctx: Context, argument: str, attribute: str, type: Type[CT]) -> CT:
        bot = ctx.bot

        match = IDConverter._get_id_match(argument) or re.match(
            r'<#([0-9]{15,20})>$', argument)
        result = None
        guild = ctx.guild

        if match is None:
            # not a mention
            if guild:
                iterable: Iterable[CT] = getattr(guild, attribute)
                result: Optional[CT] = sandwich.utils.get(
                    iterable, name=argument)
            else:

                def check(c):
                    return isinstance(c, type) and c.name == argument

                result = sandwich.utils.find(check, bot.get_all_channels())
        else:
            channel_id = int(match.group(1))
            if guild:
                result = guild.get_channel(channel_id)
            else:
                result = _get_from_guilds(bot, 'get_channel', channel_id)

        if not isinstance(result, type):
            raise ChannelNotFound(argument)

        return result

    @staticmethod
    def _resolve_thread(ctx: Context, argument: str, attribute: str, type: Type[TT]) -> TT:
        bot = ctx.bot

        match = IDConverter._get_id_match(argument) or re.match(
            r'<#([0-9]{15,20})>$', argument)
        result = None
        guild = ctx.guild

        if match is None:
            # not a mention
            if guild:
                iterable: Iterable[TT] = getattr(guild, attribute)
                result: Optional[TT] = sandwich.utils.get(
                    iterable, name=argument)
        else:
            thread_id = int(match.group(1))
            if guild:
                result = guild.get_thread(thread_id)

        if not result or not isinstance(result, type):
            raise ThreadNotFound(argument)

        return result


class TextChannelConverter(IDConverter[sandwich.TextChannel]):
    """Converts to a :class:`~sandwich.TextChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.TextChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'text_channels', sandwich.TextChannel)


class VoiceChannelConverter(IDConverter[sandwich.VoiceChannel]):
    """Converts to a :class:`~sandwich.VoiceChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.VoiceChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'voice_channels', sandwich.VoiceChannel)


class StageChannelConverter(IDConverter[sandwich.StageChannel]):
    """Converts to a :class:`~sandwich.StageChannel`.

    .. versionadded:: 1.7

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.StageChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'stage_channels', sandwich.StageChannel)


class CategoryChannelConverter(IDConverter[sandwich.CategoryChannel]):
    """Converts to a :class:`~sandwich.CategoryChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.ChannelNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.CategoryChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'categories', sandwich.CategoryChannel)


class StoreChannelConverter(IDConverter[sandwich.StoreChannel]):
    """Converts to a :class:`~sandwich.StoreChannel`.

    All lookups are via the local guild. If in a DM context, then the lookup
    is done by the global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name.

    .. versionadded:: 1.7
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.StoreChannel:
        return GuildChannelConverter._resolve_channel(ctx, argument, 'channels', sandwich.StoreChannel)


class ThreadConverter(IDConverter[sandwich.Thread]):
    """Coverts to a :class:`~sandwich.Thread`.

    All lookups are via the local guild.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name.

    .. versionadded: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Thread:
        return GuildChannelConverter._resolve_thread(ctx, argument, 'threads', sandwich.Thread)


class ColourConverter(Converter[sandwich.Colour]):
    """Converts to a :class:`~sandwich.Colour`.

    .. versionchanged:: 1.5
        Add an alias named ColorConverter

    The following formats are accepted:

    - ``0x<hex>``
    - ``#<hex>``
    - ``0x#<hex>``
    - ``rgb(<number>, <number>, <number>)``
    - Any of the ``classmethod`` in :class:`~sandwich.Colour`

        - The ``_`` in the name can be optionally replaced with spaces.

    Like CSS, ``<number>`` can be either 0-255 or 0-100% and ``<hex>`` can be
    either a 6 digit hex number or a 3 digit hex shortcut (e.g. #fff).

    .. versionchanged:: 1.5
         Raise :exc:`.BadColourArgument` instead of generic :exc:`.BadArgument`

    .. versionchanged:: 1.7
        Added support for ``rgb`` function and 3-digit hex shortcuts
    """

    RGB_REGEX = re.compile(
        r'rgb\s*\((?P<r>[0-9]{1,3}%?)\s*,\s*(?P<g>[0-9]{1,3}%?)\s*,\s*(?P<b>[0-9]{1,3}%?)\s*\)')

    def parse_hex_number(self, argument):
        arg = ''.join(
            i * 2 for i in argument) if len(argument) == 3 else argument
        try:
            value = int(arg, base=16)
            if not (0 <= value <= 0xFFFFFF):
                raise BadColourArgument(argument)
        except ValueError:
            raise BadColourArgument(argument)
        else:
            return sandwich.Color(value=value)

    def parse_rgb_number(self, argument, number):
        if number[-1] == '%':
            value = int(number[:-1])
            if not (0 <= value <= 100):
                raise BadColourArgument(argument)
            return round(255 * (value / 100))

        value = int(number)
        if not (0 <= value <= 255):
            raise BadColourArgument(argument)
        return value

    def parse_rgb(self, argument, *, regex=RGB_REGEX):
        match = regex.match(argument)
        if match is None:
            raise BadColourArgument(argument)

        red = self.parse_rgb_number(argument, match.group('r'))
        green = self.parse_rgb_number(argument, match.group('g'))
        blue = self.parse_rgb_number(argument, match.group('b'))
        return sandwich.Color.from_rgb(red, green, blue)

    async def convert(self, ctx: Context, argument: str) -> sandwich.Colour:
        if argument[0] == '#':
            return self.parse_hex_number(argument[1:])

        if argument[0:2] == '0x':
            rest = argument[2:]
            # Legacy backwards compatible syntax
            if rest.startswith('#'):
                return self.parse_hex_number(rest[1:])
            return self.parse_hex_number(rest)

        arg = argument.lower()
        if arg[0:3] == 'rgb':
            return self.parse_rgb(arg)

        arg = arg.replace(' ', '_')
        method = getattr(sandwich.Colour, arg, None)
        if arg.startswith('from_') or method is None or not inspect.ismethod(method):
            raise BadColourArgument(arg)
        return method()


ColorConverter = ColourConverter


class RoleConverter(IDConverter[sandwich.Role]):
    """Converts to a :class:`~sandwich.Role`.

    All lookups are via the local guild. If in a DM context, the converter raises
    :exc:`.NoPrivateMessage` exception.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.RoleNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Role:
        guild = ctx.guild
        if not guild:
            raise NoPrivateMessage()

        match = self._get_id_match(argument) or re.match(
            r'<@&([0-9]{15,20})>$', argument)
        if match:
            result = guild.get_role(int(match.group(1)))
        else:
            result = sandwich.utils.get(guild._roles.values(), name=argument)

        if result is None:
            raise RoleNotFound(argument)
        return result


class GameConverter(Converter[sandwich.Game]):
    """Converts to :class:`~sandwich.Game`."""

    async def convert(self, ctx: Context, argument: str) -> sandwich.Game:
        return sandwich.Game(name=argument)


class InviteConverter(Converter[sandwich.Invite]):
    """Converts to a :class:`~sandwich.Invite`.

    This is done via an HTTP request using :meth:`.Bot.fetch_invite`.

    .. versionchanged:: 1.5
         Raise :exc:`.BadInviteArgument` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Invite:
        try:
            invite = await ctx.bot.fetch_invite(argument)
            return invite
        except Exception as exc:
            raise BadInviteArgument(argument) from exc


class GuildConverter(IDConverter[sandwich.Guild]):
    """Converts to a :class:`~sandwich.Guild`.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by name. (There is no disambiguation for Guilds with multiple matching names).

    .. versionadded:: 1.7
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Guild:
        match = self._get_id_match(argument)
        result = None

        if match is not None:
            guild_id = int(match.group(1))
            result = ctx.bot.get_guild(guild_id)

        if result is None:
            result = sandwich.utils.get(ctx.bot.guilds, name=argument)

            if result is None:
                raise GuildNotFound(argument)
        return result


class EmojiConverter(IDConverter[sandwich.Emoji]):
    """Converts to a :class:`~sandwich.Emoji`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name

    .. versionchanged:: 1.5
         Raise :exc:`.EmojiNotFound` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.Emoji:
        match = self._get_id_match(argument) or re.match(
            r'<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,20})>$', argument)
        result = None
        bot = ctx.bot
        guild = ctx.guild

        if match is None:
            # Try to get the emoji by name. Try local guild first.
            if guild:
                result = sandwich.utils.get(guild.emojis, name=argument)

            if result is None:
                result = sandwich.utils.get(bot.emojis, name=argument)
        else:
            emoji_id = int(match.group(1))

            # Try to look up emoji by id.
            result = bot.get_emoji(emoji_id)

        if result is None:
            raise EmojiNotFound(argument)

        return result


class PartialEmojiConverter(Converter[sandwich.PartialEmoji]):
    """Converts to a :class:`~sandwich.PartialEmoji`.

    This is done by extracting the animated flag, name and ID from the emoji.

    .. versionchanged:: 1.5
         Raise :exc:`.PartialEmojiConversionFailure` instead of generic :exc:`.BadArgument`
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.PartialEmoji:
        match = re.match(
            r'<(a?):([a-zA-Z0-9\_]{1,32}):([0-9]{15,20})>$', argument)

        if match:
            emoji_animated = bool(match.group(1))
            emoji_name = match.group(2)
            emoji_id = int(match.group(3))

            return sandwich.PartialEmoji.with_state(
                ctx.bot._connection, animated=emoji_animated, name=emoji_name, id=emoji_id
            )

        raise PartialEmojiConversionFailure(argument)


class GuildStickerConverter(IDConverter[sandwich.GuildSticker]):
    """Converts to a :class:`~sandwich.GuildSticker`.

    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    3. Lookup by name

    .. versionadded:: 2.0
    """

    async def convert(self, ctx: Context, argument: str) -> sandwich.GuildSticker:
        match = self._get_id_match(argument)
        result = None
        bot = ctx.bot
        guild = ctx.guild

        if match is None:
            # Try to get the sticker by name. Try local guild first.
            if guild:
                result = sandwich.utils.get(guild.stickers, name=argument)

            if result is None:
                result = sandwich.utils.get(bot.stickers, name=argument)
        else:
            sticker_id = int(match.group(1))

            # Try to look up sticker by id.
            result = bot.get_sticker(sticker_id)

        if result is None:
            raise GuildStickerNotFound(argument)

        return result


class clean_content(Converter[str]):
    """Converts the argument to mention scrubbed version of
    said content.

    This behaves similarly to :attr:`~sandwich.Message.clean_content`.

    Attributes
    ------------
    fix_channel_mentions: :class:`bool`
        Whether to clean channel mentions.
    use_nicknames: :class:`bool`
        Whether to use nicknames when transforming mentions.
    escape_markdown: :class:`bool`
        Whether to also escape special markdown characters.
    remove_markdown: :class:`bool`
        Whether to also remove special markdown characters. This option is not supported with ``escape_markdown``

        .. versionadded:: 1.7
    """

    def __init__(
        self,
        *,
        fix_channel_mentions: bool = False,
        use_nicknames: bool = True,
        escape_markdown: bool = False,
        remove_markdown: bool = False,
    ) -> None:
        self.fix_channel_mentions = fix_channel_mentions
        self.use_nicknames = use_nicknames
        self.escape_markdown = escape_markdown
        self.remove_markdown = remove_markdown

    async def convert(self, ctx: Context, argument: str) -> str:
        msg = ctx.message

        if ctx.guild:

            def resolve_member(id: int) -> str:
                m = _utils_get(msg.mentions, id=id) or ctx.guild.get_member(id)
                return f'@{m.display_name if self.use_nicknames else m.name}' if m else '@deleted-user'

            def resolve_role(id: int) -> str:
                r = _utils_get(msg.role_mentions,
                               id=id) or ctx.guild.get_role(id)
                return f'@{r.name}' if r else '@deleted-role'

        else:

            def resolve_member(id: int) -> str:
                m = _utils_get(msg.mentions, id=id) or ctx.bot.get_user(id)
                return f'@{m.name}' if m else '@deleted-user'

            def resolve_role(id: int) -> str:
                return '@deleted-role'

        if self.fix_channel_mentions and ctx.guild:

            def resolve_channel(id: int) -> str:
                c = ctx.guild.get_channel(id)
                return f'#{c.name}' if c else '#deleted-channel'

        else:

            def resolve_channel(id: int) -> str:
                return f'<#{id}>'

        transforms = {
            '@': resolve_member,
            '@!': resolve_member,
            '#': resolve_channel,
            '@&': resolve_role,
        }

        def repl(match: re.Match) -> str:
            type = match[1]
            id = int(match[2])
            transformed = transforms[type](id)
            return transformed

        result = re.sub(r'<(@[!&]?|#)([0-9]{15,20})>', repl, argument)
        if self.escape_markdown:
            result = sandwich.utils.escape_markdown(result)
        elif self.remove_markdown:
            result = sandwich.utils.remove_markdown(result)

        # Completely ensure no mentions escape:
        return sandwich.utils.escape_mentions(result)


class Greedy(List[T]):
    r"""A special converter that greedily consumes arguments until it can't.
    As a consequence of this behaviour, most input errors are silently discarded,
    since it is used as an indicator of when to stop parsing.

    When a parser error is met the greedy converter stops converting, undoes the
    internal string parsing routine, and continues parsing regularly.

    For example, in the following code:

    .. code-block:: python3

        @commands.command()
        async def test(ctx, numbers: Greedy[int], reason: str):
            await ctx.send("numbers: {}, reason: {}".format(numbers, reason))

    An invocation of ``[p]test 1 2 3 4 5 6 hello`` would pass ``numbers`` with
    ``[1, 2, 3, 4, 5, 6]`` and ``reason`` with ``hello``\.

    For more information, check :ref:`ext_commands_special_converters`.
    """

    __slots__ = ('converter',)

    def __init__(self, *, converter: T):
        self.converter = converter

    def __repr__(self):
        converter = getattr(self.converter, '__name__', repr(self.converter))
        return f'Greedy[{converter}]'

    def __class_getitem__(cls, params: Union[Tuple[T], T]) -> Greedy[T]:
        if not isinstance(params, tuple):
            params = (params,)
        if len(params) != 1:
            raise TypeError('Greedy[...] only takes a single argument')
        converter = params[0]

        origin = getattr(converter, '__origin__', None)
        args = getattr(converter, '__args__', ())

        if not (callable(converter) or isinstance(converter, Converter) or origin is not None):
            raise TypeError(
                'Greedy[...] expects a type or a Converter instance.')

        if converter in (str, type(None)) or origin is Greedy:
            raise TypeError(f'Greedy[{converter.__name__}] is invalid.')

        if origin is Union and type(None) in args:
            raise TypeError(f'Greedy[{converter!r}] is invalid.')

        return cls(converter=converter)


def _convert_to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        raise BadBoolArgument(lowered)


def get_converter(param: inspect.Parameter) -> Any:
    converter = param.annotation
    if converter is param.empty:
        if param.default is not param.empty:
            converter = str if param.default is None else type(param.default)
        else:
            converter = str
    return converter


_GenericAlias = type(List[T])


def is_generic_type(tp: Any, *, _GenericAlias: Type = _GenericAlias) -> bool:
    # type: ignore
    return isinstance(tp, type) and issubclass(tp, Generic) or isinstance(tp, _GenericAlias)


CONVERTER_MAPPING: Dict[Type[Any], Any] = {
    sandwich.Object: ObjectConverter,
    sandwich.Member: MemberConverter,
    sandwich.User: UserConverter,
    sandwich.Message: MessageConverter,
    sandwich.PartialMessage: PartialMessageConverter,
    sandwich.TextChannel: TextChannelConverter,
    sandwich.Invite: InviteConverter,
    sandwich.Guild: GuildConverter,
    sandwich.Role: RoleConverter,
    sandwich.Game: GameConverter,
    sandwich.Colour: ColourConverter,
    sandwich.VoiceChannel: VoiceChannelConverter,
    sandwich.StageChannel: StageChannelConverter,
    sandwich.Emoji: EmojiConverter,
    sandwich.PartialEmoji: PartialEmojiConverter,
    sandwich.CategoryChannel: CategoryChannelConverter,
    sandwich.StoreChannel: StoreChannelConverter,
    sandwich.Thread: ThreadConverter,
    sandwich.abc.GuildChannel: GuildChannelConverter,
    sandwich.GuildSticker: GuildStickerConverter,
}


async def _actual_conversion(ctx: Context, converter, argument: str, param: inspect.Parameter):
    if converter is bool:
        return _convert_to_bool(argument)

    try:
        module = converter.__module__
    except AttributeError:
        pass
    else:
        if module is not None and (module.startswith('sandwich.') and not module.endswith('converter')):
            converter = CONVERTER_MAPPING.get(converter, converter)

    try:
        if inspect.isclass(converter) and issubclass(converter, Converter):
            if inspect.ismethod(converter.convert):
                return await converter.convert(ctx, argument)
            else:
                return await converter().convert(ctx, argument)
        elif isinstance(converter, Converter):
            return await converter.convert(ctx, argument)
    except CommandError:
        raise
    except Exception as exc:
        raise ConversionError(converter, exc) from exc

    try:
        return converter(argument)
    except CommandError:
        raise
    except Exception as exc:
        try:
            name = converter.__name__
        except AttributeError:
            name = converter.__class__.__name__

        raise BadArgument(
            f'Converting to "{name}" failed for parameter "{param.name}".') from exc


async def run_converters(ctx: Context, converter, argument: str, param: inspect.Parameter):
    """|coro|

    Runs converters for a given converter, argument, and parameter.

    This function does the same work that the library does under the hood.

    .. versionadded:: 2.0

    Parameters
    ------------
    ctx: :class:`Context`
        The invocation context to run the converters under.
    converter: Any
        The converter to run, this corresponds to the annotation in the function.
    argument: :class:`str`
        The argument to convert to.
    param: :class:`inspect.Parameter`
        The parameter being converted. This is mainly for error reporting.

    Raises
    -------
    CommandError
        The converter failed to convert.

    Returns
    --------
    Any
        The resulting conversion.
    """
    origin = getattr(converter, '__origin__', None)

    if origin is Union:
        errors = []
        _NoneType = type(None)
        union_args = converter.__args__
        for conv in union_args:
            # if we got to this part in the code, then the previous conversions have failed
            # so we should just undo the view, return the default, and allow parsing to continue
            # with the other parameters
            if conv is _NoneType and param.kind != param.VAR_POSITIONAL:
                ctx.view.undo()
                return None if param.default is param.empty else param.default

            try:
                value = await run_converters(ctx, conv, argument, param)
            except CommandError as exc:
                errors.append(exc)
            else:
                return value

        # if we're here, then we failed all the converters
        raise BadUnionArgument(param, union_args, errors)

    if origin is Literal:
        errors = []
        conversions = {}
        literal_args = converter.__args__
        for literal in literal_args:
            literal_type = type(literal)
            try:
                value = conversions[literal_type]
            except KeyError:
                try:
                    value = await _actual_conversion(ctx, literal_type, argument, param)
                except CommandError as exc:
                    errors.append(exc)
                    conversions[literal_type] = object()
                    continue
                else:
                    conversions[literal_type] = value

            if value == literal:
                return value

        # if we're here, then we failed to match all the literals
        raise BadLiteralArgument(param, literal_args, errors)

    # This must be the last if-clause in the chain of origin checking
    # Nearly every type is a generic type within the typing library
    # So care must be taken to make sure a more specialised origin handle
    # isn't overwritten by the widest if clause
    if origin is not None and is_generic_type(converter):
        converter = origin

    return await _actual_conversion(ctx, converter, argument, param)


@dataclass
class Flag:
    """Represents a flag parameter for :class:`FlagConverter`.

    The :func:`~sandwich.flag` function helps
    create these flag objects, but it is not necessary to
    do so. These cannot be constructed manually.

    Attributes
    ------------
    name: :class:`str`
        The name of the flag.
    aliases: List[:class:`str`]
        The aliases of the flag name.
    attribute: :class:`str`
        The attribute in the class that corresponds to this flag.
    default: Any
        The default value of the flag, if available.
    annotation: Any
        The underlying evaluated annotation of the flag.
    max_args: :class:`int`
        The maximum number of arguments the flag can accept.
        A negative value indicates an unlimited amount of arguments.
    override: :class:`bool`
        Whether multiple given values overrides the previous value.
    """

    name: str = MISSING
    aliases: List[str] = field(default_factory=list)
    attribute: str = MISSING
    annotation: Any = MISSING
    default: Any = MISSING
    max_args: int = MISSING
    override: bool = MISSING
    cast_to_dict: bool = False

    @property
    def required(self) -> bool:
        """:class:`bool`: Whether the flag is required.

        A required flag has no default value.
        """
        return self.default is MISSING


def flag(
    *,
    name: str = MISSING,
    aliases: List[str] = MISSING,
    default: Any = MISSING,
    max_args: int = MISSING,
    override: bool = MISSING,
) -> Any:
    """Override default functionality and parameters of the underlying :class:`FlagConverter`
    class attributes.

    Parameters
    ------------
    name: :class:`str`
        The flag name. If not given, defaults to the attribute name.
    aliases: List[:class:`str`]
        Aliases to the flag name. If not given no aliases are set.
    default: Any
        The default parameter. This could be either a value or a callable that takes
        :class:`Context` as its sole parameter. If not given then it defaults to
        the default value given to the attribute.
    max_args: :class:`int`
        The maximum number of arguments the flag can accept.
        A negative value indicates an unlimited amount of arguments.
        The default value depends on the annotation given.
    override: :class:`bool`
        Whether multiple given values overrides the previous value. The default
        value depends on the annotation given.
    """
    return Flag(name=name, aliases=aliases, default=default, max_args=max_args, override=override)


def validate_flag_name(name: str, forbidden: Set[str]):
    if not name:
        raise ValueError('flag names should not be empty')

    for ch in name:
        if ch.isspace():
            raise ValueError(f'flag name {name!r} cannot have spaces')
        if ch == '\\':
            raise ValueError(f'flag name {name!r} cannot have backslashes')
        if ch in forbidden:
            raise ValueError(
                f'flag name {name!r} cannot have any of {forbidden!r} within them')


def get_flags(namespace: Dict[str, Any], globals: Dict[str, Any], locals: Dict[str, Any]) -> Dict[str, Flag]:
    annotations = namespace.get('__annotations__', {})
    case_insensitive = namespace['__commands_flag_case_insensitive__']
    flags: Dict[str, Flag] = {}
    cache: Dict[str, Any] = {}
    names: Set[str] = set()
    for name, annotation in annotations.items():
        flag = namespace.pop(name, MISSING)
        if isinstance(flag, Flag):
            flag.annotation = annotation
        else:
            flag = Flag(name=name, annotation=annotation, default=flag)

        flag.attribute = name
        if flag.name is MISSING:
            flag.name = name

        annotation = flag.annotation = resolve_annotation(
            flag.annotation, globals, locals, cache)

        if flag.default is MISSING and hasattr(annotation, '__commands_is_flag__') and annotation._can_be_constructible():
            flag.default = annotation._construct_default

        if flag.aliases is MISSING:
            flag.aliases = []

        # Add sensible defaults based off of the type annotation
        # <type> -> (max_args=1)
        # List[str] -> (max_args=-1)
        # Tuple[int, ...] -> (max_args=1)
        # Dict[K, V] -> (max_args=-1, override=True)
        # Union[str, int] -> (max_args=1)
        # Optional[str] -> (default=None, max_args=1)

        try:
            origin = annotation.__origin__
        except AttributeError:
            # A regular type hint
            if flag.max_args is MISSING:
                flag.max_args = 1
        else:
            if origin is Union:
                # typing.Union
                if flag.max_args is MISSING:
                    flag.max_args = 1
                if annotation.__args__[-1] is type(None) and flag.default is MISSING:
                    # typing.Optional
                    flag.default = None
            elif origin is tuple:
                # typing.Tuple
                # tuple parsing is e.g. `flag: peter 20`
                # for Tuple[str, int] would give you flag: ('peter', 20)
                if flag.max_args is MISSING:
                    flag.max_args = 1
            elif origin is list:
                # typing.List
                if flag.max_args is MISSING:
                    flag.max_args = -1
            elif origin is dict:
                # typing.Dict[K, V]
                # Equivalent to:
                # typing.List[typing.Tuple[K, V]]
                flag.cast_to_dict = True
                if flag.max_args is MISSING:
                    flag.max_args = -1
                if flag.override is MISSING:
                    flag.override = True
            elif origin is Literal:
                if flag.max_args is MISSING:
                    flag.max_args = 1
            else:
                raise TypeError(
                    f'Unsupported typing annotation {annotation!r} for {flag.name!r} flag')

        if flag.override is MISSING:
            flag.override = False

        # Validate flag names are unique
        name = flag.name.casefold() if case_insensitive else flag.name
        if name in names:
            raise TypeError(
                f'{flag.name!r} flag conflicts with previous flag or alias.')
        else:
            names.add(name)

        for alias in flag.aliases:
            # Validate alias is unique
            alias = alias.casefold() if case_insensitive else alias
            if alias in names:
                raise TypeError(
                    f'{flag.name!r} flag alias {alias!r} conflicts with previous flag or alias.')
            else:
                names.add(alias)

        flags[flag.name] = flag

    return flags


class FlagsMeta(type):
    if TYPE_CHECKING:
        __commands_is_flag__: bool
        __commands_flags__: Dict[str, Flag]
        __commands_flag_aliases__: Dict[str, str]
        __commands_flag_regex__: Pattern[str]
        __commands_flag_case_insensitive__: bool
        __commands_flag_delimiter__: str
        __commands_flag_prefix__: str

    def __new__(
        cls: Type[type],
        name: str,
        bases: Tuple[type, ...],
        attrs: Dict[str, Any],
        *,
        case_insensitive: bool = MISSING,
        delimiter: str = MISSING,
        prefix: str = MISSING,
    ):
        attrs['__commands_is_flag__'] = True

        try:
            global_ns = sys.modules[attrs['__module__']].__dict__
        except KeyError:
            global_ns = {}

        frame = inspect.currentframe()
        try:
            if frame is None:
                local_ns = {}
            else:
                if frame.f_back is None:
                    local_ns = frame.f_locals
                else:
                    local_ns = frame.f_back.f_locals
        finally:
            del frame

        flags: Dict[str, Flag] = {}
        aliases: Dict[str, str] = {}
        for base in reversed(bases):
            if base.__dict__.get('__commands_is_flag__', False):
                flags.update(base.__dict__['__commands_flags__'])
                aliases.update(base.__dict__['__commands_flag_aliases__'])
                if case_insensitive is MISSING:
                    attrs['__commands_flag_case_insensitive__'] = base.__dict__[
                        '__commands_flag_case_insensitive__']
                if delimiter is MISSING:
                    attrs['__commands_flag_delimiter__'] = base.__dict__[
                        '__commands_flag_delimiter__']
                if prefix is MISSING:
                    attrs['__commands_flag_prefix__'] = base.__dict__[
                        '__commands_flag_prefix__']

        if case_insensitive is not MISSING:
            attrs['__commands_flag_case_insensitive__'] = case_insensitive
        if delimiter is not MISSING:
            attrs['__commands_flag_delimiter__'] = delimiter
        if prefix is not MISSING:
            attrs['__commands_flag_prefix__'] = prefix

        case_insensitive = attrs.setdefault(
            '__commands_flag_case_insensitive__', False)
        delimiter = attrs.setdefault('__commands_flag_delimiter__', ':')
        prefix = attrs.setdefault('__commands_flag_prefix__', '')

        for flag_name, flag in get_flags(attrs, global_ns, local_ns).items():
            flags[flag_name] = flag
            aliases.update(
                {alias_name: flag_name for alias_name in flag.aliases})

        forbidden = set(delimiter).union(prefix)
        for flag_name in flags:
            validate_flag_name(flag_name, forbidden)
        for alias_name in aliases:
            validate_flag_name(alias_name, forbidden)

        regex_flags = 0
        if case_insensitive:
            flags = {key.casefold(): value for key, value in flags.items()}
            aliases = {key.casefold(): value.casefold()
                       for key, value in aliases.items()}
            regex_flags = re.IGNORECASE

        keys = list(re.escape(k) for k in flags)
        keys.extend(re.escape(a) for a in aliases)
        keys = sorted(keys, key=lambda t: len(t), reverse=True)

        joined = '|'.join(keys)
        pattern = re.compile(
            f'(({re.escape(prefix)})(?P<flag>{joined}){re.escape(delimiter)})', regex_flags)
        attrs['__commands_flag_regex__'] = pattern
        attrs['__commands_flags__'] = flags
        attrs['__commands_flag_aliases__'] = aliases

        return type.__new__(cls, name, bases, attrs)


async def tuple_convert_all(ctx: Context, argument: str, flag: Flag, converter: Any) -> Tuple[Any, ...]:
    view = StringView(argument)
    results = []
    param: inspect.Parameter = ctx.current_parameter  # type: ignore
    while not view.eof:
        view.skip_ws()
        if view.eof:
            break

        word = view.get_quoted_word()
        if word is None:
            break

        try:
            converted = await run_converters(ctx, converter, word, param)
        except CommandError:
            raise
        except Exception as e:
            raise BadFlagArgument(flag) from e
        else:
            results.append(converted)

    return tuple(results)


async def tuple_convert_flag(ctx: Context, argument: str, flag: Flag, converters: Any) -> Tuple[Any, ...]:
    view = StringView(argument)
    results = []
    param: inspect.Parameter = ctx.current_parameter  # type: ignore
    for converter in converters:
        view.skip_ws()
        if view.eof:
            break

        word = view.get_quoted_word()
        if word is None:
            break

        try:
            converted = await run_converters(ctx, converter, word, param)
        except CommandError:
            raise
        except Exception as e:
            raise BadFlagArgument(flag) from e
        else:
            results.append(converted)

    if len(results) != len(converters):
        raise BadFlagArgument(flag)

    return tuple(results)


async def convert_flag(ctx, argument: str, flag: Flag, annotation: Any = None) -> Any:
    param: inspect.Parameter = ctx.current_parameter  # type: ignore
    annotation = annotation or flag.annotation
    try:
        origin = annotation.__origin__
    except AttributeError:
        pass
    else:
        if origin is tuple:
            if annotation.__args__[-1] is Ellipsis:
                return await tuple_convert_all(ctx, argument, flag, annotation.__args__[0])
            else:
                return await tuple_convert_flag(ctx, argument, flag, annotation.__args__)
        elif origin is list:
            # typing.List[x]
            annotation = annotation.__args__[0]
            return await convert_flag(ctx, argument, flag, annotation)
        elif origin is Union and annotation.__args__[-1] is type(None):
            # typing.Optional[x]
            annotation = Union[annotation.__args__[:-1]]
            return await run_converters(ctx, annotation, argument, param)
        elif origin is dict:
            # typing.Dict[K, V] -> typing.Tuple[K, V]
            return await tuple_convert_flag(ctx, argument, flag, annotation.__args__)

    try:
        return await run_converters(ctx, annotation, argument, param)
    except CommandError:
        raise
    except Exception as e:
        raise BadFlagArgument(flag) from e


F = TypeVar('F', bound='FlagConverter')


class FlagConverter(metaclass=FlagsMeta):
    """A converter that allows for a user-friendly flag syntax.

    The flags are defined using :pep:`526` type annotations similar
    to the :mod:`dataclasses` Python module. For more information on
    how this converter works, check the appropriate
    :ref:`documentation <ext_commands_flag_converter>`.

    .. container:: operations

        .. describe:: iter(x)

            Returns an iterator of ``(flag_name, flag_value)`` pairs. This allows it
            to be, for example, constructed as a dict or a list of pairs.
            Note that aliases are not shown.

    .. versionadded:: 2.0

    Parameters
    -----------
    case_insensitive: :class:`bool`
        A class parameter to toggle case insensitivity of the flag parsing.
        If ``True`` then flags are parsed in a case insensitive manner.
        Defaults to ``False``.
    prefix: :class:`str`
        The prefix that all flags must be prefixed with. By default
        there is no prefix.
    delimiter: :class:`str`
        The delimiter that separates a flag's argument from the flag's name.
        By default this is ``:``.
    """

    @classmethod
    def get_flags(cls) -> Dict[str, Flag]:
        """Dict[:class:`str`, :class:`Flag`]: A mapping of flag name to flag object this converter has."""
        return cls.__commands_flags__.copy()

    @classmethod
    def _can_be_constructible(cls) -> bool:
        return all(not flag.required for flag in cls.__commands_flags__.values())

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        for flag in self.__class__.__commands_flags__.values():
            yield (flag.name, getattr(self, flag.attribute))

    @classmethod
    async def _construct_default(cls: Type[F], ctx: Context) -> F:
        self: F = cls.__new__(cls)
        flags = cls.__commands_flags__
        for flag in flags.values():
            if callable(flag.default):
                default = await maybe_coroutine(flag.default, ctx)
                setattr(self, flag.attribute, default)
            else:
                setattr(self, flag.attribute, flag.default)
        return self

    def __repr__(self) -> str:
        pairs = ' '.join(
            [f'{flag.attribute}={getattr(self, flag.attribute)!r}' for flag in self.get_flags().values()])
        return f'<{self.__class__.__name__} {pairs}>'

    @classmethod
    def parse_flags(cls, argument: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        flags = cls.__commands_flags__
        aliases = cls.__commands_flag_aliases__
        last_position = 0
        last_flag: Optional[Flag] = None

        case_insensitive = cls.__commands_flag_case_insensitive__
        for match in cls.__commands_flag_regex__.finditer(argument):
            begin, end = match.span(0)
            key = match.group('flag')
            if case_insensitive:
                key = key.casefold()

            if key in aliases:
                key = aliases[key]

            flag = flags.get(key)
            if last_position and last_flag is not None:
                value = argument[last_position: begin - 1].lstrip()
                if not value:
                    raise MissingFlagArgument(last_flag)

                try:
                    values = result[last_flag.name]
                except KeyError:
                    result[last_flag.name] = [value]
                else:
                    values.append(value)

            last_position = end
            last_flag = flag

        # Add the remaining string to the last available flag
        if last_position and last_flag is not None:
            value = argument[last_position:].strip()
            if not value:
                raise MissingFlagArgument(last_flag)

            try:
                values = result[last_flag.name]
            except KeyError:
                result[last_flag.name] = [value]
            else:
                values.append(value)

        # Verification of values will come at a later stage
        return result

    @classmethod
    async def convert(cls: Type[F], ctx: Context, argument: str) -> F:
        """|coro|

        The method that actually converters an argument to the flag mapping.

        Parameters
        ----------
        cls: Type[:class:`FlagConverter`]
            The flag converter class.
        ctx: :class:`Context`
            The invocation context.
        argument: :class:`str`
            The argument to convert from.

        Raises
        --------
        FlagError
            A flag related parsing error.
        CommandError
            A command related error.

        Returns
        --------
        :class:`FlagConverter`
            The flag converter instance with all flags parsed.
        """
        arguments = cls.parse_flags(argument)
        flags = cls.__commands_flags__

        self: F = cls.__new__(cls)
        for name, flag in flags.items():
            try:
                values = arguments[name]
            except KeyError:
                if flag.required:
                    raise MissingRequiredFlag(flag)
                else:
                    if callable(flag.default):
                        default = await maybe_coroutine(flag.default, ctx)
                        setattr(self, flag.attribute, default)
                    else:
                        setattr(self, flag.attribute, flag.default)
                    continue

            if flag.max_args > 0 and len(values) > flag.max_args:
                if flag.override:
                    values = values[-flag.max_args:]
                else:
                    raise TooManyFlags(flag, values)

            # Special case:
            if flag.max_args == 1:
                value = await convert_flag(ctx, values[0], flag)
                setattr(self, flag.attribute, value)
                continue

            # Another special case, tuple parsing.
            # Tuple parsing is basically converting arguments within the flag
            # So, given flag: hello 20 as the input and Tuple[str, int] as the type hint
            # We would receive ('hello', 20) as the resulting value
            # This uses the same whitespace and quoting rules as regular parameters.
            values = [await convert_flag(ctx, value, flag) for value in values]

            if flag.cast_to_dict:
                values = dict(values)  # type: ignore

            setattr(self, flag.attribute, values)

        return self
