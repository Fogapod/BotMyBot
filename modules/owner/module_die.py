from objects.modulebase import ModuleBase
from objects.permissions import PermissionBotOwner

from constants import STOP_EXIT_CODE


class Module(ModuleBase):

    usage_doc = '{prefix}{aliases} [exit_code]'
    short_doc = 'Terminate bot process'

    name = 'stop'
    aliases = (name, 'die', '!')
    category = 'Owner'
    user_perms = (PermissionBotOwner(), )
    hidden = True

    async def on_call(self, message, ctx, **options):
        try:
            await message.add_reaction('✅')
        except Exception:
            pass

        exit_code = args[1] if len(args) == 2 else STOP_EXIT_CODE
        self.bot.stop(exit_code)