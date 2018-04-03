class ArgParser:

    def __init__(self, string):
        self.args = []
        self.flags = {}
        self._separators = []

        self._split(string)
        self._parse_flags()

    @classmethod
    def parse(cls, string):
        return cls(string)

    def _split(self, string):
        args, seps = [], []
        index = 0
        quote = None
        is_previous_space = True

        s = string.strip()

        while s:
            q_buff = ''
            c = s[:1]

            while c in ('\'', '"'):
                if not q_buff or q_buff[0] == c:
                    q_buff += c
                else:
                    break

                if len(s) > len(q_buff):
                    c = s[len(q_buff)]
                else:
                    c = ''

            s = s[len(q_buff):]

            if quote == q_buff and s and s[0].isspace():
                quote = None
            elif quote is None and q_buff and is_previous_space:
                quote = q_buff
            elif q_buff:
                c = q_buff + c

            if c.isspace() and not quote:
                if is_previous_space:
                    seps[index - 1] += c
                else:
                    seps.append(c)
                    index += 1
                is_previous_space = True
            elif c != quote:
                if is_previous_space:
                    args.append(c)
                else:
                    args[index] += c
                is_previous_space = False

            s = s[1:]

            # print(f'Char {"[" + c + "]":<3} Str {"[" + s + "]":<20} Quote {quote}')

        self.args = args
        self._separators = seps

        return args, seps

    def _parse_flags(self):
        flags = {}

        self.flags = flags

        return flags

    def __len__(self):
        return len(self.args)

    def __bool__(self):
        return len(self.args) != 0

    def __str__(self):
        return str(self.args)

    def __getitem__(self, value):
        if isinstance(value, slice):
            if value.step is not None:
                raise ValueError('Arguments object does not support slicing with step')

            seps = self._separators + ['']
            result = ''

            for i in range(value.start or 0, value.stop or len(self.args)):
                result += self.args[i] + seps[i]
            return result
        else:
            return self.args[value]