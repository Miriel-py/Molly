# vote.py

from math import ceil
import re
from typing import Dict, Optional

import discord

from cache import messages
from database import reminders, users
from resources import emojis, exceptions, functions, regex, strings


async def process_message(bot: discord.Bot, message: discord.Message, embed_data: Dict, user: Optional[discord.User],
                          user_settings: Optional[users.User]) -> bool:
    """Processes the message for all vote related actions.

    Returns
    -------
    - True if a logo reaction should be added to the message
    - False otherwise
    """
    return_values = []
    return_values.append(await create_vote_reminder(message, embed_data, user, user_settings))
    return any(return_values)


async def create_vote_reminder(message: discord.Message, embed_data: Dict, user: Optional[discord.User],
                               user_settings: Optional[users.User]) -> bool:
    """Create a reminder when the vote embed is opened and on cooldown. If not on cooldown, show info to open it.

    Returns
    -------
    - True if a logo reaction should be added to the message
    - False otherwise
    """
    add_reaction = False
    search_strings = [
        'you can vote for idle farm', #All languages
    ]
    if any(search_string in embed_data['description'].lower() for search_string in search_strings):
        if user is None:
            user_command_message = (
                await messages.find_message(message.channel.id, regex.COMMAND_VOTE)
            )
            user = user_command_message.author
        if user_settings is None:
            try:
                user_settings: users.User = await users.get_user(user.id)
            except exceptions.FirstTimeUserError:
                return add_reaction
        if not user_settings.bot_enabled or not user_settings.reminder_vote.enabled: return add_reaction
        user_command = await functions.get_game_command(user_settings, 'vote')
        timestring_match = re.search(r'cooldown: \*\*(.+?)\*\*\n', embed_data['field0']['value'].lower())
        energy_refill_amount_match = re.search(r'energy refill\*\*: (\d+)%', embed_data['field0']['value'].lower())
        energy_refill_amount = int(energy_refill_amount_match.group(1))
        energy_from_vote = ceil(user_settings.energy_max * energy_refill_amount / 100)
        energy_regen_time = await functions.get_energy_regen_time(user_settings)
        try:
            current_energy = await functions.get_current_energy_amount(user_settings, energy_regen_time)
        except (exceptions.EnergyFullTimeOutdatedError, exceptions.EnergyFullTimeNoneError):
            if not timestring_match:
                await message.reply(strings.MSG_ENERGY_OUTDATED.format(user=user.display_name,
                                                                       cmd_profile=strings.SLASH_COMMANDS["profile"]))
                return
        if not timestring_match:
            answer = (
                f'➜ You will have **{current_energy + energy_from_vote:,}**/**{user_settings.energy_max}** '
                f'{emojis.ENERGY} after voting.'
            )
            if current_energy + energy_from_vote > user_settings.energy_max:
                answer = (
                    f'➜ You will have {emojis.WARNING}**{current_energy + energy_from_vote:,}**/**{user_settings.energy_max}**{emojis.WARNING} '
                    f'{emojis.ENERGY} after voting.\n'
                    f'➜ Go use some energy first.'
                )
            else:
                answer = (
                    f'{answer}\n'
                    f'➜ Use {strings.SLASH_COMMANDS["vote"]} again after voting to create the reminder\n'
                )
            await message.reply(answer)
            return add_reaction
        timestring = timestring_match.group(1)
        time_left = await functions.calculate_time_left_from_timestring(message, timestring)
        reminder_message = (
            user_settings.reminder_vote.message
            .replace('{command}', user_command)
        )
        reminder: reminders.Reminder = (
            await reminders.insert_user_reminder(user.id, 'vote', time_left, message.channel.id, reminder_message)
        )
        if reminder.record_exists and user_settings.reactions_enabled: add_reaction = True
    return add_reaction