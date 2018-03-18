from objects.logger import Logger

logger = Logger()

import traceback
import asyncio
import time
import sys

import discord

from objects.modulemanager import ModuleManager
from objects.config import Config
from objects.redisdb import RedisDB

from constants import STOP_EXIT_CODE, ERROR_EXIT_CODE
from utils.formatters import format_response, trim_message
from utils import funcs


class BotMyBot(discord.Client):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # will be used as process exit code after stopping if not None
        self.exit_code = None

        # used to prevent reloading commands in on_ready after reconnect
        self.is_first_on_ready_event = True

        # timestamp of bot launch, filled in first on_ready call
        self.start_time = 0

        # bot will react only to stored messages 
        self.tracked_messages = {}

        self.config = Config('config.json', loop=self.loop)
        logger.verbosity = self.config.get('logger_verbosity', logger.VERBOSITY_INFO)
        logger.add_file(self.config.get('logs_file', None))

        logger.debug('Logger ................. connected')

        self.token = self.config.get('token', None)
        self.is_dev = self.config.get('is_dev', False)

        self.mm = ModuleManager(self)
        logger.debug('ModuleManager .......... connected')

        self.redis = RedisDB()
        logger.debug('RedisDB ................ connected')

        self._default_prefixes = {}
        self._mention_prefixes = {}
        self.prefixes = []
        self._guild_prefixes = {}

        self._last_messages = {}

    @property
    def uptime(self):
        return time.time() - self.start_time

    async def init_prefixes(self):
        bot_id = self.user.id

        self.prefixes = []
        self._default_prefixes = [await self.redis.get('prefix', default='+')]
        self._mention_prefixes = [f'<@{bot_id}>', f'<@!{bot_id}>']
        self.prefixes.extend([*self._default_prefixes, *self._mention_prefixes])

        self._guild_prefixes = {}
        for p in await self.redis.execute('KEYS', 'guild_prefix:*'):
            guild_id = int(p[len('guild_prefix:'):])
            self._guild_prefixes[guild_id] = await self.redis.get(p)

    def run(self, token=None):
        if token is None:
            token = self.token
        else:
            self.token = token

        if token is None:
            token = input('Token not provided. Please, insert it into config file or paste here for single bot launch: ')

        super(BotMyBot, self).run(token, reconnect=True, fetch_offline_members=True)

    def restart(self):
        self.stop(0)

    def stop(self, exit_code=STOP_EXIT_CODE, force=False):
        if force:
            import sys
            sys.exit(exit_code)
        self.redis.disconnect()
        logger.debug('Stopping event loop and cancelling tasks')
        self.loop.stop()
        tasks = asyncio.gather(*asyncio.Task.all_tasks(), loop=self.loop)
        tasks.cancel()

        self.exit_code = exit_code

    async def on_ready(self):
        if not self.is_first_on_ready_event:
            await self.mm.init_modules()
            logger.info('Bot reconnected')
            return

        self.is_first_on_ready_event = False

        redis_port = self.config.get('redis_port', None)
        try:
            await self.redis.connect(port=redis_port)
        except ConnectionRefusedError:
            logger.info('Failed to connect to redis! Stopping bot')
            logger.info(traceback.format_exc())
            self.stop(ERROR_EXIT_CODE, force=True)
        logger.info('Connected to redis db with %s keys' % await self.redis.get_db_size())

        await self.mm.load_modules()
        logger.info('Loaded modules: [%s]' % ' '.join(self.mm.modules.keys()))

        await self.init_prefixes()

        self.start_time = time.time()
        logger.info('Bot ready')

        if self.is_dev:
            logger.info('Is a dev instance')
        if len(self._default_prefixes) == 1:
            logger.info('Default prefix: ' + self._default_prefixes[0])
        else:
            logger.info('Default prefixes: [' + ' '.join(self._default_prefixes) + ']')

    async def on_error(self, event, *args, **kwargs):
        pass

    async def close(self):
        await super().close()
        logger.info('Connection closed')

    async def on_message(self, msg, from_edit=False):
        self.register_last_user_message(msg)

        if msg.author.bot:
            return

        if not from_edit:
            await self.track_message(msg)

        lower_content = msg.content.lower()
        clean_content = None

        prefixes = self.prefixes

        if msg.guild is not None:
            guild_prefixes = self._guild_prefixes.get(msg.guild.id, None)

            if guild_prefixes:
                prefixes = [guild_prefixes] + self._mention_prefixes
        else:
            prefixes = prefixes + ['']

        for p in prefixes:
            if lower_content.startswith(p):
                clean_content = msg.content[len(p):].lstrip()
                break

        if clean_content is None:
            return

        module_response = await self.mm.check_modules(msg, clean_content)

        if module_response:
            module_response = await format_response(
                module_response, msg, self)

        if module_response:
            await self.send_message(
                msg, content=module_response, response_to=msg)

    def register_last_user_message(self, msg):
        if msg.channel.id not in self._last_messages:
            self._last_messages[msg.channel.id] = {msg.author.id: msg}
        else:
            self._last_messages[msg.channel.id][msg.author.id] = msg

    async def on_message_edit(self, before, after):
        if before.content == after.content:
            return

        if before.id in self.tracked_messages:
            await self.clear_responses_to_message(before.id)
            await self.on_message(after, from_edit=True)

    async def on_message_delete(self, message):
        if message.id in self.tracked_messages:
            await self.clear_responses_to_message(message.id)

    async def clear_responses_to_message(self, message_id):
        if len(self.tracked_messages[message_id]) > 0:
            for message in self.tracked_messages[message_id]:
                await self.delete_message(message)
            self.tracked_messages[message_id] = []

    async def send_message(self, msg, response_to=None, replace_everyone=True, replace_mentions=True, **fields):
        content = fields.pop('content', '')
        content = content.replace(self.token, 'TOKEN_LEAKED')

        if replace_everyone:
            content = content.replace('@everyone', '@\u200beveryone')
            content = content.replace('@here', '@\u200bhere')
        if replace_mentions:
            content = await funcs.replace_mentions(content, self)

        content = trim_message(content)
        fields['content'] = content

        message = None

        try:
            message = await msg.channel.send(**fields)
        except Exception:
            exception = traceback.format_exc()
            exception = '\n'.join(exception.split('\n')[-4:])
            exception = f'❗ Message delivery failed\n```\n{exception}```'
            message = await msg.channel.send(exception)
        finally:
            if response_to is not None and message is not None:
                await self.register_response(response_to, message)

            return message

    async def edit_message(self, message, replace_everyone=True, replace_mentions=True, **fields):
        content = fields.pop('content', '')
        content = content.replace(self.token, 'TOKEN_LEAKED')

        if replace_everyone:
            content = content.replace('@everyone', '@\u200beveryone')
            content = content.replace('@here', '@\u200bhere')
        if replace_mentions:
            content = await funcs.replace_mentions(content, self)

        content = trim_message(content)
        fields['content'] = content

        try:
            return await message.edit(**fields)
        except discord.errors.NotFound:
            logger.debug('edit_message: message not found')
            return None
        except Exception:
            exception = traceback.format_exc()
            exception = '\n'.join(exception.split('\n')[-4:])
            exception = f'❗ Message edit failed\n```\n{exception}```'
            return await message.edit(content=exception)
    
    async def delete_message(self, message):
        try:
            return await message.delete()
        except discord.errors.NotFound:
            logger.debug('delete_message: message not found')
            return

    async def track_message(self, message):
        if message.id in self.tracked_messages:
            return

        self.tracked_messages[message.id] = []
        self.loop.call_later(300, self.release_tracked_message, message.id)

    def release_tracked_message(self, message_id):
        del self.tracked_messages[message_id]

    async def register_response(self, request, response):
        if request.id in self.tracked_messages:
            self.tracked_messages[request.id].append(response)
        else:
            logger.debug('Request outdated, not registering')