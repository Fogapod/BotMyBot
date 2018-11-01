import re
import random
import asyncio

from dateutil.relativedelta import relativedelta
from datetime import datetime

import discord

from objects.bot import KiwiBot
from objects.logger import Logger

from constants import (
    ID_REGEX, USER_MENTION_OR_ID_REGEX, ROLE_OR_ID_REGEX,
    CHANNEL_OR_ID_REGEX, COLOUR_REGEX, TIME_REGEX, EMOJI_REGEX
)


bot = KiwiBot.get_bot()
logger = Logger.get_logger()


async def create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    ):
    process = await asyncio.create_subprocess_exec(
        *args, stdout=stdout, stderr=stderr
    )
    return process, process.pid


async def create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    ):
    process = await asyncio.create_subprocess_shell(
        command, stdout=stdout, stderr=stderr
    )
    return process, process.pid


async def execute_process(process):
    stdout, stderr = await process.communicate()

    return stdout, stderr


async def find_user(pattern, msg, strict_guild=False, max_count=1, global_search=False):
    user = None
    id_match = USER_MENTION_OR_ID_REGEX.fullmatch(pattern)

    if id_match is not None:
        user_id = int(id_match.group(1) or id_match.group(0))
        if msg.guild is not None:
            user = msg.guild.get_member(user_id)
        if user is None:
            # double check of msg.guild, but we need to ensure we won't
            # get member object from other guild by accident
            for guild in bot.guilds or []:
                user = guild.get_member(user_id)
                if user is not None:
                    break

        if user is None and not strict_guild:
            try:
                user = await bot.get_user_info(user_id)
            except discord.NotFound:
                pass

    if user is not None:
        return user if max_count == 1 else [user]

    if msg.guild is None:
        return None

    found = []
    pattern = pattern.lower()

    for guild in bot.guilds if global_search else [msg.guild]:
        for member in guild.members:
            match_pos = -1
            if member.nick is not None and not global_search:
                match_pos = member.nick.lower().find(pattern)
            if match_pos == -1:
                match_pos = (member.name + '#' + member.discriminator).lower().find(pattern)
            if match_pos == -1:
                continue
            found.append((member, match_pos))

    found = list(set(found))
    found.sort(
        key=lambda x: (
            # last member message timestamp, lower delta is better
            _get_last_user_message_timestamp(x[0].id, msg.channel.id),
            # index of match in string, smaller value is better
            -x[1],
            # member status, not 'offline' is better
            str(x[0].status) != 'offline',
            # guild join timestamp, lower delta is better
            x[0].joined_at
        ), reverse=True
    )

    if found:
        if max_count == 1:
            return found[0][0]
        elif max_count == -1:
            return [u for u, mp in found]
        else:
            [u for u, mp in found[:max_count]]

    return None


async def find_role(pattern, guild, max_count=1):
    id_match = ROLE_OR_ID_REGEX.fullmatch(pattern)

    if id_match is not None:
        role_id = int(id_match.group(1) or id_match.group(0))
        # role = guild.get_role(role_id)
        # if role is not None:
        #     return role
        for role in guild.roles:
            if role.id == role_id:
                return role if max_count == 1 else [role]

    found = []
    pattern = pattern.lower()

    for role in guild.roles if guild is not None else []:
        match_pos = role.name.lower().find(pattern)
        if match_pos != -1:
            found.append((role, match_pos))

    found.sort(key=lambda x: x[1])

    if found:
        if max_count == 1:
            return found[0][0]
        elif max_count == -1:
            return [r for r, mp in found]
        else:
            [r for r, mp in found[:max_count]]

    return None


async def find_guild(pattern, max_count=1):
    id_match = ID_REGEX.fullmatch(pattern)

    if id_match is not None:
        guild_id = int(id_match.group(0))
        guild = bot.get_guild(guild_id)
        if guild is not None:
            return guild if max_count == 1 else [guild]

    found = []
    pattern = pattern.lower()

    for guild in bot.guilds:
        match_pos = guild.name.lower().find(pattern)
        if match_pos != -1:
            found.append((guild, match_pos))

    found.sort(
        key=lambda x: (x[0].member_count, x[1]),
        reverse=True
    )

    if found:
        if max_count == 1:
            return found[0][0]
        elif max_count == -1:
            return [g for g, mp in found]
        else:
            [g for g, mp in found[:max_count]]

    return None

find_server = find_guild


async def find_channel(
    pattern, guild, max_count=1, global_id_search=False, global_search=False,
    include_direct=False, include_text=True, include_voice=True, include_category=True
    ):
    found = []
    id_match = CHANNEL_OR_ID_REGEX.fullmatch(pattern)

    if id_match is not None:
        channel_id = int(id_match.group(1) or id_match.group(0))
        channel = None

        if global_id_search:
            channel = bot.get_channel(channel_id)
            if isinstance(channel, discord.DMChannel):
                channel = None
        elif guild is not None:
            channel = guild.get_channel(channel_id)
        if channel is not None:
            found.append((channel, 0))
    else:
        for channel in bot.get_all_channels() if global_search else guild.channels if guild is not None else ():
            if isinstance(channel, discord.TextChannel) and not include_text:
                continue
            if isinstance(channel, discord.VoiceChannel) and not include_voice:
                continue
            if isinstance(channel, discord.CategoryChannel) and not include_category:
                continue

            match_pos = channel.name.lower().find(pattern)
            if match_pos != -1:
                found.append((channel, match_pos))

    found.sort(key=lambda x: (x[1], x[0].name))

    if found:
        if max_count == 1:
            return found[0][0]
        elif max_count == -1:
            return [c for c, mp in found]
        else:
            [c for c, mp in found[:max_count]]

    return None


async def _find_image(pattern, ctx, *, limit=200, include_gif=True, download_timeout=10):
    """Returns array with url and bytes fields that can be missing"""

    static_formats = ('png', 'jpg', 'webp')
    default_static_format = 'png'

    img = {
        'url': None,
        'bytes': None
    }

    if pattern:
        # check if pattern is custom emoji
        emoji_match = EMOJI_REGEX.fullmatch(pattern)
        if emoji_match:
            groups = emoji_match.groupdict()
            emoji_id = int(groups['id'])

            emoji = ctx.bot.get_emoji(emoji_id)
            if emoji:
                img['url'] = emoji.url
                return img

            fmt = 'gif' if include_gif else default_static_format
            async with ctx.bot.sess.get(
                    f'https://cdn.discordapp.com/emojis/{emoji_id}.{fmt}', timeout=download_timeout) as r:
                if r.status != 200:  # image not found
                    return img

                img['url'] = r.url
                img['bytes'] = await r.read()
            return img

        # check if pattern is normal emoji
        # thanks NotSoSuper#0001 for the API
        def to_string(c):
            digit = f'{ord(c):x}'
            return f'{digit:>04}'

        code = '-'.join(map(to_string, pattern))
        async with ctx.bot.sess.get(
                f'https://bot.mods.nyc/twemoji/{code}.png', timeout=download_timeout) as r:
            if r.status == 200:
                img['url'] = r.url
                img['bytes'] = await r.read()
                return img

        # check if pattern is user mention
        user = await find_user(pattern, ctx.message)
        if user:
            img['url'] = user.avatar_url_as(
                format='gif' if user.is_avatar_animated() and include_gif else default_static_format)
            return img

        # check if pattern is url
        if pattern.startswith('<') and pattern.endswith('>'):
            pattern = pattern[1:-1]
        if not pattern.startswith(('http://', 'https://')):
            return img

        proxy = random.choice(list(ctx.bot.proxies.keys()))
        try:
            r = await ctx.bot.sess.get(
                pattern, proxy=proxy, timeout=download_timeout, raise_for_status=True)
            if r.content_length > 7000000:
                return img
            fmt = r.content_type.partition('/')[-1]
            if fmt == 'gif':
                if not include_gif:
                    return img
            else:
                if fmt not in static_formats:
                    return img

            img['url'] = r.url
            img['bytes'] = await r.read()
            return img
        except Exception as e:
            return img

    # check channel history for attachments
    # command can be invoked by message edit, but we still want to check messages before created_at
    history = await ctx.channel.history(limit=limit, before=ctx.message.created_at).flatten()
    for m in [ctx.message] + history:
        # check attachments (files uploaded to discord)
        for attachment in m.attachments:
            file_fmt = attachment.filename.lower().partition('.')[-1]
            if file_fmt == 'gif':
                if not include_gif:
                    continue
            else:
                if file_fmt not in static_formats:
                    continue

            img['url'] = attachment.url
            return img

        # check embeds (user posted image url)
        for embed in m.embeds:
            # TODO: handle 'rich' embed
            if embed.type != 'image':
                continue

            img['url'] = embed.url
            return img

    return img


async def find_image(pattern, ctx, download_timeout=10, **kwargs):
    """Returns image bytes, is a wrapper for _find_image"""

    img = await _find_image(pattern, ctx, download_timeout=download_timeout, **kwargs)
    if img['bytes']:
        return img['bytes']
    if not img['url']:
        return None

    async with ctx.bot.sess.get(
            img['url'], timeout=download_timeout, raise_for_status=True) as r:
        return await r.read()


def _get_last_user_message_timestamp(user_id, channel_id):
    # ts = await bot.redis.get(f'last_message_timestamp:{channel_id}:{author_id}')
    channel = bot._last_messages.get(channel_id)
    if channel is not None:
        if user_id in channel:
            return channel[user_id]

    return datetime.fromtimestamp(0)


async def get_local_prefix(msg):
    if msg.guild is not None:
        guild_prefix = bot._guild_prefixes.get(msg.guild.id)
        if guild_prefix is not None:
            return guild_prefix
    return bot._default_prefix


async def request_reaction_confirmation(msg, user, emoji_accept='✅', emoji_cancel='❌', timeout=20):
    try:
        for emoji in (emoji_accept, emoji_cancel):
            await msg.add_reaction(emoji)
    except discord.NotFound:
        return False

    def check(reaction, member):
        return all((
            member == user,
            reaction.message.id == msg.id,
            str(reaction.emoji) in (emoji_accept, emoji_cancel)
         ))

    try:
        reaction, member = await bot.wait_for('reaction_add', timeout=timeout, check=check)
    except asyncio.TimeoutError:
        try:
            await msg.clear_reactions()
        except Exception:
            pass
        return None
    else:
        if str(reaction) == emoji_accept:
            try:
                await msg.clear_reactions()
            except Exception:
                pass

            return True
    try:
        await msg.clear_reactions()
    except Exception:
        pass

    return False


def colour_from_string(string):
    match = COLOUR_REGEX.fullmatch(string)
    if match is None:
        raise ValueError('Not a colour')
    return discord.Colour(int(match.group(1), 16))


def timedelta_from_string(string):
    if string.isdigit():  # use value as seconds
        values = [0] * 6 + [int(string)]
    else:
        matches = TIME_REGEX.findall(string)
        values = [sum(int(i) if i.isdigit() else 0 for i in row) for row in zip(*matches)]
        if sum(values) == 0:
            raise ValueError('Invalid input')

    names = ['years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds']
    data = {n: v for n, v in zip(names, values)}
    now = datetime.now()

    return now + relativedelta(**data)  # OverflowError possible


def check_permission(permission, channel, user):
	if not permission.check(channel, user):
		raise permission
