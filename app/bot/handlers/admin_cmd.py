import logging
import time
from aiogram import Bot, Router, types
from aiogram.filters import Command
from sqlalchemy import select

from app.bot.utils.admin_cache import is_user_admin
from app.bot.utils.command_parser import extract_target_and_args, parse_duration
from app.bot.utils.permissions import RESTRICTED_PERMISSIONS, UNRESTRICTED_PERMISSIONS
from app.core.database import async_session_maker
from app.models.audit_log import AuditLog
from app.models.warning import UserWarning

logger = logging.getLogger(__name__)
router = Router()

AUTO_PUNISH_MUTE_SECONDS = 24 * 3600


async def record_audit_log(
    chat_id: int,
    moderator_id: int,
    target_id: int,
    action: str,
    duration_sec: int | None = None,
    reason: str | None = None,
):
    async with async_session_maker() as session:
        log = AuditLog(
            chat_id=chat_id,
            moderator_id=moderator_id,
            target_id=target_id,
            action=action,
            duration_sec=duration_sec,
            reason=reason,
        )
        session.add(log)
        await session.commit()


@router.message(Command("mute"))
async def cmd_mute(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    if not await is_user_admin(bot, chat_id, message.from_user.id):
        return

    target, args = extract_target_and_args(message)
    if not target:
        await message.reply("Usage: Reply to a user with `/mute <duration> [reason]` (e.g. `/mute 30m spam`)")
        return

    if await is_user_admin(bot, chat_id, target.id) or target.id == bot.id:
        await message.reply("Cannot moderate fellow administrators or the bot.")
        return

    duration_str = args[0] if args else "15m"
    duration_sec = parse_duration(duration_str) or 900
    reason = " ".join(args[1:]) if len(args) > 1 else "No reason specified"

    until_timestamp = int(time.time() + duration_sec)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=RESTRICTED_PERMISSIONS,
            until_date=until_timestamp,
        )
        await record_audit_log(chat_id, message.from_user.id, target.id, "MUTE", duration_sec, reason)
        await message.reply(
            f"🔇 **{target.full_name}** has been muted for {duration_str}.\n**Reason:** {reason}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to mute user %s: %s", target.id, e)
        await message.reply("Failed to mute user. Ensure the bot has administrative privileges.")


@router.message(Command("unmute"))
async def cmd_unmute(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    if not await is_user_admin(bot, chat_id, message.from_user.id):
        return

    target, _ = extract_target_and_args(message)
    if not target:
        await message.reply("Usage: Reply to a user with `/unmute`")
        return

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=UNRESTRICTED_PERMISSIONS,
        )
        await record_audit_log(chat_id, message.from_user.id, target.id, "UNMUTE")
        await message.reply(f"🔊 Restored permissions for **{target.full_name}**.", parse_mode="Markdown")
    except Exception as e:
        logger.error("Failed to unmute user %s: %s", target.id, e)
        await message.reply("Failed to unmute user.")


@router.message(Command("ban"))
async def cmd_ban(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    if not await is_user_admin(bot, chat_id, message.from_user.id):
        return

    target, args = extract_target_and_args(message)
    if not target:
        await message.reply("Usage: Reply to a user with `/ban [duration] [reason]` (e.g. `/ban 7d raid`)")
        return

    if await is_user_admin(bot, chat_id, target.id) or target.id == bot.id:
        await message.reply("Cannot ban fellow administrators or the bot.")
        return

    duration_sec = None
    reason = "No reason specified"

    if args:
        parsed_sec = parse_duration(args[0])
        if parsed_sec:
            duration_sec = parsed_sec
            reason = " ".join(args[1:]) if len(args) > 1 else reason
        else:
            reason = " ".join(args)

    until_timestamp = int(time.time() + duration_sec) if duration_sec else 0

    try:
        await bot.ban_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            until_date=until_timestamp if until_timestamp else None,
        )
        await record_audit_log(chat_id, message.from_user.id, target.id, "BAN", duration_sec, reason)
        duration_desc = f"for {args[0]}" if duration_sec else "permanently"
        await message.reply(
            f"🚫 **{target.full_name}** has been banned {duration_desc}.\n**Reason:** {reason}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to ban user %s: %s", target.id, e)
        await message.reply("Failed to ban user.")


@router.message(Command("warn"))
async def cmd_warn(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    if not await is_user_admin(bot, chat_id, message.from_user.id):
        return

    target, args = extract_target_and_args(message)
    if not target:
        await message.reply("Usage: Reply to a user with `/warn [reason]`")
        return

    if await is_user_admin(bot, chat_id, target.id) or target.id == bot.id:
        await message.reply("Cannot issue warnings to administrators.")
        return

    reason = " ".join(args) if args else "Rule violation"

    async with async_session_maker() as session:
        query = select(UserWarning).where(
            UserWarning.chat_id == chat_id,
            UserWarning.user_id == target.id,
        )
        result = await session.execute(query)
        warn_entry = result.scalar_one_or_none()

        if not warn_entry:
            warn_entry = UserWarning(chat_id=chat_id, user_id=target.id, strike_count=1)
            session.add(warn_entry)
        else:
            warn_entry.strike_count += 1

        current_strikes = warn_entry.strike_count
        await session.commit()

    await record_audit_log(chat_id, message.from_user.id, target.id, "WARN", reason=reason)

    if current_strikes >= 3:
        async with async_session_maker() as session:
            query = select(UserWarning).where(
                UserWarning.chat_id == chat_id,
                UserWarning.user_id == target.id,
            )
            res = await session.execute(query)
            entry = res.scalar_one_or_none()
            if entry:
                entry.strike_count = 0
                await session.commit()

        until_ts = int(time.time() + AUTO_PUNISH_MUTE_SECONDS)
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target.id,
                permissions=RESTRICTED_PERMISSIONS,
                until_date=until_ts,
            )
            await record_audit_log(
                chat_id,
                bot.id,
                target.id,
                "AUTO_MUTE",
                AUTO_PUNISH_MUTE_SECONDS,
                "Reached 3 warnings threshold",
            )
            await message.reply(
                f"⚠️ **{target.full_name}** has reached **3/3 strikes** and has been muted for 24 hours.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Failed to auto-mute user %s on 3rd warning: %s", target.id, e)
    else:
        await message.reply(
            f"⚠️ **Warning [{current_strikes}/3]** issued to **{target.full_name}**.\n**Reason:** {reason}",
            parse_mode="Markdown",
        )