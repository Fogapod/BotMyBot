import re

import discord

from constants import USER_MENTION_REGEX, ROLE_MENTION_REGEX


def trim_text(text, max_len=2000):
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len // 2 - 3] + '\n...\n' + text[-max_len // 2 + 2:]

    return text


async def replace_mentions(content, channel, bot, strict=False):
    """No longer used."""

    if strict:
        content = _escape_special_chars(content)

    for mid in USER_MENTION_REGEX.findall(content):
        mid = int(mid)
        user = None

        if getattr(channel, 'guild', None) is not None:
            user = channel.guild.get_member(mid)
        if user is None:
            user = discord.utils.get(bot.users, id=mid)
        if user is None:
            try:
                user = await bot.get_user_info(mid)
            except discord.NotFound:
                continue

        content = re.sub(f'<@!?{user.id}>', f'@{user}', content)

    for rim in ROLE_MENTION_REGEX.findall(content):
        rim = int(rim)
        if getattr(channel, 'guild', None) is not None:
            role = discord.utils.get(channel.guild.roles, id=rim)
        else:
            break

        if role is None:
            continue

        content = content.replace(f'<@&{role.id}>', f'@{role}')

    return content


def replace_mass_mentions(content, strict=False):
    """No longer used."""

    if strict:
        content = _escape_special_chars(content)

    return content.replace('@everyone', '@\u200beveryone').replace('@here', '@\u200bhere')


def _escape_special_chars(content):
    """No longer used."""

    content = content.replace("\N{RIGHT-TO-LEFT OVERRIDE}", "")

    if len(content) > 300:  # https://github.com/discordapp/discord-api-docs/issues/1241
        content = content[:300] + content[300:].replace('@', '@ ')

    return content


def lazy_format(s, *args, **kwargs):
    while True:
        try:
            return s.format(*args, **kwargs)
        except KeyError as e:
            key = e.args[0]
            kwargs[key] = "{%s}" % key
        except (ValueError, AttributeError, IndexError, TypeError):
            return s


def cleanup_code(text):
    lang = None
    if len(text) > 6 and text[:3] == '```' and text[-3:] == '```':
        text = text[3:-3]
        lang = ''
        for i, c in enumerate(text):
            if c.isspace():
                if c == '\n':
                    break
            else:
                lang += c
        text = text[i + 1:]
    return text, lang
