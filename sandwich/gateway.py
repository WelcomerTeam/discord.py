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

from collections import namedtuple
import logging
import time

from . import utils
from .activity import BaseActivity
from .errors import InvalidArgument

_log = logging.getLogger(__name__)

__all__ = (
    'DiscordWebSocket',
)


EventListener = namedtuple('EventListener', 'predicate event result future')


class DiscordWebSocket:
    """Implements a WebSocket for Discord's gateway v6.
    """

    def __init__(self, *, loop):
        self.loop = loop

        # an empty dispatcher to prevent crashes
        self._dispatch = lambda *args: None
        # generic event listeners
        self._dispatch_listeners = []

    def debug_log_receive(self, data, /):
        self._dispatch('socket_raw_receive', data)

    def log_receive(self, _, /):
        pass

    @classmethod
    def from_client(cls, client):
        """Creates a main websocket for Discord from a :class:`Client`.

        This is for internal use only.
        """
        ws = DiscordWebSocket(loop=client.loop)

        # dynamically add attributes needed
        ws._connection = client._connection
        ws._discord_parsers = client._connection.parsers
        ws._dispatch = client.dispatch

        return ws

    def wait_for(self, event, predicate, result=None):
        """Waits for a DISPATCH'd event that meets the predicate.

        Parameters
        -----------
        event: :class:`str`
            The event name in all upper case to wait for.
        predicate
            A function that takes a data parameter to check for event
            properties. The data parameter is the 'd' key in the JSON message.
        result
            A function that takes the same data parameter and executes to send
            the result to the future. If ``None``, returns the data.

        Returns
        --------
        asyncio.Future
            A future to wait for.
        """

        future = self.loop.create_future()
        entry = EventListener(
            event=event, predicate=predicate, result=result, future=future)
        self._dispatch_listeners.append(entry)
        return future

    def handle_dispatch(self, event: str, data: any) -> None:
        try:
            func = self._discord_parsers[event]
        except KeyError:
            _log.debug('Unknown event %s.', event)
        else:
            func(data)

        # remove the dispatched listeners
        removed = []
        for index, entry in enumerate(self._dispatch_listeners):
            if entry.event != event:
                continue

            future = entry.future
            if future.cancelled():
                removed.append(index)
                continue

            try:
                valid = entry.predicate(data)
            except Exception as exc:
                future.set_exception(exc)
                removed.append(index)
            else:
                if valid:
                    ret = data if entry.result is None else entry.result(data)
                    future.set_result(ret)
                    removed.append(index)

        for index in reversed(removed):
            del self._dispatch_listeners[index]

    async def send_as_json(self, data):
        await self.send(utils._to_json(data))

    async def change_presence(self, *, activity=None, status=None, since=0.0):
        if activity is not None:
            if not isinstance(activity, BaseActivity):
                raise InvalidArgument(
                    'activity must derive from BaseActivity.')
            activity = [activity.to_dict()]
        else:
            activity = []

        if status == 'idle':
            since = int(time.time() * 1000)

        payload = {
            'op': self.PRESENCE,
            'd': {
                'activities': activity,
                'afk': False,
                'since': since,
                'status': status
            }
        }

        sent = utils._to_json(payload)
        _log.debug('Sending "%s" to change status', sent)
        await self.send(sent)

    async def request_chunks(self, guild_id, query=None, *, limit, user_ids=None, presences=False, nonce=None):
        payload = {
            'op': self.REQUEST_MEMBERS,
            'd': {
                'guild_id': guild_id,
                'presences': presences,
                'limit': limit
            }
        }

        if nonce:
            payload['d']['nonce'] = nonce

        if user_ids:
            payload['d']['user_ids'] = user_ids

        if query is not None:
            payload['d']['query'] = query

        await self.send_as_json(payload)
