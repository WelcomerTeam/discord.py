import asyncio
import logging
import signal
import traceback
from datetime import datetime

import grpc
from stan.aio.client import Msg

from sandwich import utils, Bot
from sandwich.abc import SandwichEvent, SandwichPayload
from sandwich.ext.sandwich.channel import Channel
from sandwich.ext.sandwich.connections.stan import StanConnection
from sandwich.ext.sandwich.sandwich import SandwichBase
from sandwich.protobuf.events_pb2 import FetchConsumerConfigurationRequest, FetchConsumerConfigurationResponse, ListenResponse


logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)

loop = asyncio.get_event_loop()

grpc_channel = grpc.aio.insecure_channel("127.0.0.1:15000")
channel = Channel(channel=grpc_channel)
connection = StanConnection(loop=loop)

swch = SandwichBase(connection=connection, channel=channel)

bot = Bot(command_prefix="//", connection=connection,
          channel=channel, loop=loop)


@bot.event
async def on_message(message):
    print(datetime.now(), message.author, message.content)
    await bot.process_commands(message)

swch.add_bot("welcomer", bot)


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
    await channel.connect()
    channel.register_hook(on_grpc_message)

    await connection.connect(cluster_id="cluster", client_id="client")
    connection.register_hook(on_mq_message)
    connection.register_hook_exception(on_mq_exception)

    res: FetchConsumerConfigurationResponse = await bot.channel.stub.FetchConsumerConfiguration(FetchConsumerConfigurationRequest())
    print(res.file)

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
