from commands.commandbase import CommandBase

import io
import sys
import asyncio
import traceback

import textwrap
from contextlib import redirect_stdout

class Command(CommandBase):
    """{prefix}{keywords} <code>
    
    Eval python code.
    {protection} or higher permission level required to use"""

    name = 'eval'
    keywords = (name, )
    arguments_required = 0
    protection = 2

    def on_load(self):
        self._last_result = None

    async def on_call(self, message):
        program = ' '.join(message.content.strip().split(' ')[1:])

        glob = {
            'bot': self.bot,
            'message': message,
            '_': self._last_result
        }

        glob.update(globals())

        fake_stdout = io.StringIO()

        to_compile = 'async def func():\n' + textwrap.indent(program, '  ')

        try:
            exec(to_compile, glob)
        except Exception as e:
            return '```py\n%s: %s\n```' % (e.__class__.__name__, e)

        func = glob['func']

        try:
            with redirect_stdout(fake_stdout):
                result = await func()
        except Exception as e:
            output = fake_stdout.getvalue()
            return '```py\n%s%s\n```' %(output, traceback.format_exc())
        else:
            output = fake_stdout.getvalue()

            if result is None:
                if output:
                    return '```py\n%s\n```' % output
            else:
                self._last_result = result

            return '```py\n%s%s\n```' % (output, result if result else 'Evaluated')