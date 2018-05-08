from objects.modulebase import ModuleBase

from utils.funcs import create_subprocess_exec, execute_process

import re


class Module(ModuleBase):

    usage_doc = '{prefix}{aliases} [url]'
    short_doc = 'Get bot response time / ping url'

    name = 'ping'
    aliases = (name, )

    async def on_call(self, msg, args, **flags):
        ping_msg = await self.send(msg, 'Pinging ...')

        if len(args) == 2:
            domain = args[1]
            if domain.startswith('<') and domain.endswith('>'):
                domain = domain[1:-1]
            if re.fullmatch('https?://.+', domain):
                domain = re.sub('^https?://|/$', '', domain)
            program = ['ping', '-c', '4', domain.encode('idna')]
            process, pid = await create_subprocess_exec(*program)
            stdout, stderr = await execute_process(process, program)

            if process.returncode in (0, 1):  # (successful ping, 100% package loss)
                return await self.bot.edit_message(
                    ping_msg, f'```\n{stdout.decode() or stderr.decode()}```')

        msg_timestamp = msg.edited_at or msg.created_at
        delta = round((ping_msg.created_at.timestamp() - msg_timestamp.timestamp()) * 1000)

        result = f'Pong, it took `{int(delta)}ms`'

        target = args[1:]
        result += f' to ping `{target}`' if target else ' to respond'

        await self.bot.edit_message(ping_msg, result)