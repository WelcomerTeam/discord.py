import asyncio
import logging
import signal

import aiohttp
import grpc
from stan.aio.client import Msg
import traceback

from sandwich import utils
from sandwich.ext.commands import Bot
from sandwich.ext.sandwich import SandwichBase
from sandwich.ext.sandwich.abc import SandwichEvent, SandwichPayload
from sandwich.ext.sandwich.channel import Channel
from sandwich.ext.sandwich.connections.stan import StanConnection
from sandwich.protobuf.discord_pb2 import Message
from sandwich.protobuf.events_pb2 import ListenResponse
from sandwich.gateway import DiscordWebSocket
from sandwich.user import ClientUser

from datetime import datetime

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)

loop = asyncio.get_event_loop()

swch = SandwichBase()


async def on_mq_message(msg: Msg):
    msg: SandwichPayload = utils._from_json(msg.data)
    ev = SandwichEvent(msg)
    swch.dispatch(ev)


async def on_mq_exception(err: Exception):
    print("mqe ", err)
    traceback.print_exception(err)


async def on_grpc_message(msg: ListenResponse):
    print("grpc ", len(msg.data))


async def start(loop):
    grpc_channel = grpc.aio.insecure_channel("127.0.0.1:15000")
    channel = Channel(channel=grpc_channel)

    await channel.connect()
    channel.register_hook(on_grpc_message)

    # BOT START

    bot = Bot(command_prefix="//", stub=channel.stub, loop=loop)

    @bot.event
    async def on_message(message):
        print(datetime.now(), message.author, message.content)
        await bot.process_commands(message)

    swch.add_bot("welcomer", bot)

    # BOT END

    connection = StanConnection(loop=loop)

    await connection.connect(cluster_id="cluster", client_id="client")
    connection.register_hook(on_mq_message)
    connection.register_hook_exception(on_mq_exception)

    channel_task = loop.create_task(channel.listen())
    connection_task = loop.create_task(connection.start(subject="sandwich"))


def run(loop):
    asyncio.ensure_future(start(loop), loop=loop)

    try:
        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    except NotImplementedError:
        pass

    loop.run_forever()


run(loop)
