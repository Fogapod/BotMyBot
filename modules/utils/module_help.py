from objects.modulebase import ModuleBase
from objects.permissions import PermissionEmbedLinks

from utils.funcs import get_local_prefix

from discord import Embed, Colour


class Module(ModuleBase):

    usage_doc = '{prefix}{aliases} [alias]'
    short_doc = 'Get information about bot or module (if given).'

    name = 'help'
    aliases = (name, 'commands')
    required_perms = (PermissionEmbedLinks, )

    async def on_call(self, msg, *args, **flags):
        # temporary solution
        args = list(args)
        if '-d' in args:
            args.remove('-d')
            flags['show-disabled'] = True
        if '--show-disabled' in args:
            args.remove('--show-disabled')
            flags['show-disabled'] = True
        if '-h' in args:
            args.remove('-h')
            flags['show-hidden'] = True
        if '--show-hidden' in args:
            args.remove('--show-hidden')
            flags['show-hidden'] = True

        if len(args) == 1:
            module_list = []
            for name, module in self.bot.mm.modules.items():
                if module.disabled:
                    if not flags.get('show-disabled', False):
                        continue
                if module.hidden:
                    if not flags.get('show-hidden', False):
                        continue

                module_list.append((name, module))

            help_text  = '```\n'
            help_text += '\n'.join(sorted([f'{m.aliases[0]:<20}{m.short_doc}' for n, m in module_list]))
            help_text += '\n```'

            embed = Embed(
                colour=Colour.gold(), title='Available commands:',
                description=help_text
            )
            embed.set_footer(
                text='Current prefix: ' + await get_local_prefix(msg, self.bot) + '\n')

            await self.send(msg, embed=embed)
            return

        if len(args) > 2:
            return '{warning} help for subcommands is not supported yet'

        module = self.bot.mm.get_module(args[1].lower())

        if not module or module.disabled:
            return '{warning} Command `' + args[1] + '` not found'

        return await module.on_doc_request(msg)