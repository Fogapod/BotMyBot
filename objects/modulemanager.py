import os
import sys
import asyncio
import traceback

from importlib import reload

from sentry_sdk import capture_exception, configure_scope

from objects.logger import Logger
from objects.argparser import ArgParser
from objects.permissions import Permission
from objects.moduleexceptions import *


logger = Logger.get_logger()

class ModuleManager:
    
    def __init__(self, bot):
        self.bot = bot
        self.modules = {}
        self._modules = {}

    async def load_modules(self, module_dirs=['modules'], strict_mode=True):
        modules_found = []

        for path, dirs, files in os.walk(module_dirs[0]):
            for f in files:
                if f.startswith('module_') and f.endswith('.py'):
                    modules_found.append(path + os.sep + f)

        logger.trace(f'Found {len(modules_found)} modules')
        for module_path in modules_found:
            module_name = module_path[module_path.rfind(os.sep) + 8:-3]
            try:
                module = await self.load_module(module_path)
                if module is None:
                    continue

                await self.init_module(module, from_reload=False)
            except Exception:
                capture_exception()
                logger.info(f'Failed to load module {module_name}')
                logger.info(traceback.format_exc())

                if strict_mode:
                    raise

                module.disabled = True
                    
        logger.trace(f'Loaded {len(self.modules)} modules')

    async def load_module(self, module_path):
        logger.trace(f'Loading module from {module_path}')
        imported = __import__(
            module_path.replace(os.sep, '.')[:-3], fromlist=['Module'])
        module = getattr(imported, 'Module')(self.bot)

        if module.disabled:
            logger.info(f'skipping disabled module {module_path}')

            return None

        self.modules[module.name]  = module
        self._modules[module.name] = imported

        return module

    async def init_modules(self, from_reload=True):
        for module in self.modules.values():
            await self.init_module(module, from_reload=from_reload)

    async def init_module(self, module, from_reload=True):
        logger.trace(f'Calling {module.name} on_load')
        await module.on_load(from_reload)

    async def reload_modules(self):
        for module_name in self.modules:
            try:
                await self.reload_module(module_name)
            except Exception:
                capture_exception()
                logger.info(
                    f'Failed reloading module {module_name} ({self._modules[module_name].__file__})')
                logger.debug(traceback.format_exc())
                raise

    async def reload_module(self, name):
        logger.trace(f'Calling {name} on_unload')
        try:
            await self.modules[name].on_unload()
        except Exception:
            capture_exception()
            logger.debug('Exception occured calling on_unload')
            logger.debug(traceback.format_exc())

        logger.trace(f'Reloading module {name}')
        reloaded = reload(self._modules[name])
        module = getattr(reloaded, 'Module')(self.bot)

        await self.init_module(module, from_reload=True)

        self._modules[name] = reloaded
        self.modules[name] = module

    async def unload_module(self, name):
        pass

    async def check_modules(self, ctx, clean_content):
        args = ArgParser.parse(clean_content)

        for name, module in self.modules.items():
            if module.disabled:
                continue
            try:
                if not await module.check_message(ctx, args):
                    continue
            except GuildOnly:
                return await module.on_guild_check_failed(ctx)
            except NSFWPermissionDenied:
                return await module.on_nsfw_permission_denied(ctx)
            except NotEnoughArgs:
                return await module.on_not_enough_arguments(ctx)
            except TooManyArgs:
                return await module.on_too_many_arguments(ctx)
            except MissingPermissions as e:
                return await module.on_missing_permissions(ctx, *e.missing)
            except Ratelimited as e:
                return await module.on_ratelimit(ctx, e.time_left)
            except Exception:
                capture_exception()
                logger.info(f'Failed to check command, stopped on module {name}')
                logger.info(traceback.format_exc())

                return

            command_output = None

            try:
                logger.trace(
                    f'{ctx.author}-{ctx.author.id} -> {module.name} in ' +
                    ('direct messages' if ctx.guild is None else f'{ctx.guild}-{ctx.guild.id}')
                )
                await self.bot.redis.incr(f'command_usage:{module.name}')
                try:
                    self.bot.dispatch('command_use', module, ctx, args)
                except Exception:
                    capture_exception()
                    logger.debug(f'Error dispatching command_use event')
                    logger.debug(traceback.format_exc())

                task = self.bot.loop.create_task(
                    module.call_command(ctx, args, **args.flags))

                self.bot._commands_in_progress[ctx.message.id] = task

                command_output = await task
            except Permission as p:
                command_output = await module.on_missing_permissions(ctx, p)
            except asyncio.CancelledError:
                logger.trace(f'Command {name} by {ctx.author} was cancelled')
            except Exception as e:
                with configure_scope() as scope:
                    scope.user = {"id": ctx.author.id, "tag": str(ctx.author)}
                    scope.set_tag("message_id", ctx.message.id)

                    if ctx.guild is None:
                        scope.set_tag("channel_dm", True)
                    else:
                        scope.set_tag("channel_dm", False)
                        scope.set_tag("guild_id", ctx.guild.id)
                        scope.set_tag("channel_id", ctx.channel.id)

                capture_exception()

                module_tb = traceback.format_exc()
                logger.info(f'Error occured calling {name}')
                logger.info(module_tb)
                logger.trace(f'Calling {name} on_error')
                try:
                    command_output = await module.on_error(e, module_tb, ctx)
                except Exception:
                    capture_exception()
                    logger.debug(f'Error occured calling {name} on_error')
                    logger.debug(traceback.format_exc())
            finally:
                del self.bot._commands_in_progress[ctx.message.id]

            return command_output

    def get_all_modules(self, hidden=False, disabled=False):
        return [
            m for m in self.modules.values()
            if m.hidden <= hidden and m.disabled <= disabled
        ]

    def get_modules_by_category(self, category):
        return [
            m for m in self.modules.values()
            if not m.disabled and m.category.lower() == (category.lower() or 'uncategorized')
        ]

    def get_module(self, alias):
        alias = alias.lower()
        for name, module in self.modules.items():
            if not module.disabled and alias in module.aliases or alias == module.name:
                return module

        return None
