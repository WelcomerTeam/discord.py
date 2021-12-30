import asyncio
import logging
import signal
import traceback
from datetime import datetime

import grpc
from stan.aio.client import Msg

from sandwich import Bot, utils
from sandwich.daemon import SandwichEvent, SandwichIdentifiers, SandwichPayload
from sandwich.ext.sandwich.channel import Channel
from sandwich.ext.sandwich.connections.stan import StanConnection
from sandwich.sandwich import SandwichBase
from sandwich.protobuf.events_pb2 import (FetchConsumerConfigurationRequest,
                                          FetchConsumerConfigurationResponse,
                                          ListenResponse)

loop = asyncio.get_event_loop()

grpc_channel = grpc.aio.insecure_channel("127.0.0.1:15000")
channel = Channel(channel=grpc_channel)
connection = StanConnection(loop=loop)

swch = SandwichBase(connection=connection, channel=channel)

bot = Bot(command_prefix="//", connection=connection,
          channel=channel, loop=loop, identifiers=swch._identifiers)


@bot.event
async def on_message(message):
    if message.author.id != 330416853971107840:
        return
    print(datetime.now(), message.author, message.content)
    await bot.process_commands(message)

swch.add_bot("welcomer", bot)


async def on_mq_message(msg: Msg):
    msg: SandwichPayload = utils._from_json(msg.data)
    ev = SandwichEvent(msg)
    await swch.dispatch(ev)


async def on_grpc_message(msg: ListenResponse):
    msg: SandwichPayload = utils._from_json(msg.data)
    ev = SandwichEvent(msg)
    await swch.dispatch(ev)


async def on_mq_exception(err: Exception):
    traceback.print_exception(err)


async def start(loop):
    await channel.connect()
    channel.register_hook(on_grpc_message)

    await connection.connect(cluster_id="cluster", client_id="client")
    connection.register_hook(on_mq_message)
    connection.register_hook_exception(on_mq_exception)

    await swch.fetch_identifiers()

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
