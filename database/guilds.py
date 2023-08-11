# guilds.py
"""Provides access to the table "guilds" in the database"""


from dataclasses import dataclass
import itertools
import sqlite3
from typing import List, Tuple, Union

import discord
from discord.ext import commands
from typing import NamedTuple

from database import errors
from resources import exceptions, settings, strings


# Containers
class EventPing(NamedTuple):
    name: str
    enabled: bool
    message: str


@dataclass()
class Guild():
    """Object that represents a record from table "guilds"."""
    event_energy: EventPing
    event_hire: EventPing
    event_lucky: EventPing
    event_packing: EventPing
    guild_id: int
    prefix: str

    async def refresh(self) -> None:
        """Refreshes guild data from the database."""
        new_settings = await get_guild(self.guild_id)
        self.prefix = new_settings.prefix
        self.event_energy = new_settings.event_energy
        self.event_hire = new_settings.event_hire
        self.event_lucky = new_settings.event_lucky
        self.event_packing = new_settings.event_packing

    async def update(self, **kwargs) -> None:
        """Updates the guild record in the database. Also calls refresh().

        Arguments
        ---------
        kwargs (column=value):
            prefix: str
            event_energy_enabled: bool
            event_energy_message: str
            event_hire_enabled: bool
            event_hire_message: str
            event_lucky_enabled: bool
            event_lucky_message: str
            event_packing_enabled: bool
            event_packing_message: str
        """
        await _update_guild(self.guild_id, **kwargs)
        await self.refresh()


# Miscellaneous functions
async def _dict_to_guild(record: dict) -> Guild:
    """Creates a Guild object from a database record

    Arguments
    ---------
    record: Database record from table "guilds" as a dict.

    Returns
    -------
    Guild object.

    Raises
    ------
    LookupError if something goes wrong reading the dict. Also logs this error to the database.
    """
    function_name = '_dict_to_guild'
    try:
        guild = Guild(
            event_energy = EventPing(
                name = 'Energy ritual',
                enabled = bool(record['event_energy_enabled']),
                message = record['event_energy_message'],
            ),
            event_hire = EventPing(
                name = 'Fired worker',
                enabled = bool(record['event_hire_enabled']),
                message = record['event_hire_message'],
            ),
            event_lucky = EventPing(
                name = 'Lucky reward',
                enabled = bool(record['event_lucky_enabled']),
                message = record['event_lucky_message'],
            ),
            event_packing = EventPing(
                name = 'Packing boxes',
                enabled = bool(record['event_packing_enabled']),
                message = record['event_packing_message'],
            ),
            guild_id = record['guild_id'],
            prefix = record['prefix'],
        )
    except Exception as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_DICT_TO_OBJECT.format(function=function_name, record=record)
        )
        raise LookupError(error)

    return guild


async def _get_mixed_case_prefixes(prefix: str) -> List[str]:
    """Turns a string into a list of all mixed case variations of said string

    Returns
    -------
    All mixed case variations: List[str]
    """
    mixed_prefixes = []
    all_prefixes = map(''.join, itertools.product(*((char.upper(), char.lower()) for char in prefix)))
    for prefix in list(all_prefixes):
        mixed_prefixes.append(prefix)
    return mixed_prefixes


# Read data
async def get_prefix(ctx_or_message: Union[commands.Context, discord.Message]) -> str:
    """Check database for stored prefix. If no prefix is found, the default prefix is used"""
    table = 'guilds'
    function_name = 'get_prefix'
    sql = f'SELECT prefix FROM {table} WHERE guild_id=?'
    guild_id = ctx_or_message.guild.id
    try:
        cur=settings.DATABASE.cursor()
        cur.execute(sql, (guild_id,))
        record = cur.fetchone()
        prefix = record['prefix'].replace('"','') if record else settings.DEFAULT_PREFIX
    except sqlite3.Error as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_SQLITE3.format(error=error, table=table, function=function_name, sql=sql),
            ctx_or_message
        )

    return prefix


async def get_all_prefixes(bot: commands.Bot, ctx: commands.Context) -> Tuple:
    """Gets all prefixes. If no prefix is found, a record for the guild is created with the
    default prefix.

    Returns
    -------
    A tuple with the current server prefix and the pingable bot

    Raises
    ------
    sqlite3.Error if something happened within the database.  Also logs this error to the database.
    """
    table = 'guilds'
    function_name = 'get_all_prefixes'
    sql = f'SELECT prefix FROM {table} WHERE guild_id=?'
    guild_id = ctx.guild.id    
    try:
        cur = settings.DATABASE.cursor()
        cur.execute(sql, (guild_id,))
        record = cur.fetchone()
        prefixes = []
        if record:
            prefix_db = record['prefix'].replace('"','')
            prefix_db_mixed_case = await _get_mixed_case_prefixes(prefix_db)
            for prefix in prefix_db_mixed_case:
                prefixes.append(prefix)
        else:
            await insert_guild(guild_id)
            prefix_default_mixed_case = await _get_mixed_case_prefixes(settings.DEFAULT_PREFIX)
            for prefix in prefix_default_mixed_case:
                prefixes.append(prefix)
    except sqlite3.Error as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_SQLITE3.format(error=error, table=table, function=function_name, sql=sql),
            ctx
        )
        raise

    return commands.when_mentioned_or(*prefixes)(bot, ctx)


async def get_guild(guild_id: int) -> Guild:
    """Gets all guild settings.

    Returns
    -------
    Guild object

    Raises
    ------
    sqlite3.Error if something happened within the database.
    exceptions.NoDataFoundError if no guild was found.
    LookupError if something goes wrong reading the dict.
    Also logs all errors to the database.
    """
    table = 'guilds'
    function_name = 'get_guild'
    sql_select = f'SELECT * FROM {table} WHERE guild_id=?'
    try:
        cur = settings.DATABASE.cursor()
        cur.execute(sql_select, (guild_id,))
        record = cur.fetchone()
    except sqlite3.Error as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_SQLITE3.format(error=error, table=table, function=function_name, sql=sql_select)
        )
        raise
    if not record:
        guild = await insert_guild(guild_id)
    else:
        guild = await _dict_to_guild(dict(record))
    return guild


# Write Data
async def _update_guild(guild_id: int, **kwargs) -> None:
    """Updates guild record. Use Guild.update() to trigger this function.

    Arguments
    ---------
    kwargs (column=value):
        prefix: str
        event_energy_enabled: bool
        event_energy_message: str
        event_hire_enabled: bool
        event_hire_message: str
        event_lucky_enabled: bool
        event_lucky_message: str
        event_packing_enabled: bool
        event_packing_message: str

    Raises
    ------
    sqlite3.Error if something happened within the database.
    NoArgumentsError if no kwargs are passed (need to pass at least one)
    Also logs all errors to the database.
    """
    table = 'guilds'
    function_name = '_update_guild'
    if not kwargs:
        await errors.log_error(
            strings.INTERNAL_ERROR_NO_ARGUMENTS.format(table=table, function=function_name)
        )
        raise exceptions.NoArgumentsError('You need to specify at least one keyword argument.')
    try:
        cur = settings.DATABASE.cursor()
        sql = f'UPDATE {table} SET'
        for kwarg in kwargs:
            sql = f'{sql} {kwarg} = :{kwarg},'
        sql = sql.strip(",")
        kwargs['guild_id'] = guild_id
        sql = f'{sql} WHERE guild_id = :guild_id'
        cur.execute(sql, kwargs)
    except sqlite3.Error as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_SQLITE3.format(error=error, table=table, function=function_name, sql=sql)
        )
        raise


async def insert_guild(guild_id: int) -> Guild:
    """Inserts a record in the table "guilds".

    Returns
    -------
    Guild object with the newly created guild.

    Raises
    ------
    sqlite3.Error if something happened within the database.
    Also logs all errors to the database.
    """
    function_name = 'insert_guild'
    table = 'guilds'
    columns = ''
    values = [guild_id, settings.DEFAULT_PREFIX]
    for event, default_message in strings.DEFAULT_MESSAGES_EVENTS.items():
        columns = f'{columns},event_{event}_message'
        values.append(default_message)
    sql = f'INSERT INTO {table} (guild_id,prefix{columns}) VALUES ('
    for value in values:
        sql = f'{sql}?,'
    sql = f'{sql.strip(",")})'
    try:
        cur = settings.DATABASE.cursor()
        cur.execute(sql, values)    
    except sqlite3.Error as error:
        await errors.log_error(
            strings.INTERNAL_ERROR_SQLITE3.format(error=error, table=table, function=function_name, sql=sql)
        )
        raise
    guild = await get_guild(guild_id)
    return guild