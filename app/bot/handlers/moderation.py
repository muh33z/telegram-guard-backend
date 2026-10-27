import asyncio
import logging
import time
from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from sqlalchemy import select

from app.bot.utils.admin_cache import is_user_admin
from app.bot.utils.anti_flood import check_flood_breach
from app.bot.utils.link_detector import contains_link, contains_telegram_invite
from app.bot.utils.permissions import RESTRICTED_PERMISSIONS
from app.core.database import async_session_maker
from app.models.group import GroupSetting

logger = logging.getLogger(__name__)
router = Router()

MUTE_DURATION_SECONDS = 15 * 60

async def send_temp_warning(bot: Bot, chat_id: int, text: str, delay_sec: int = 5):
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text)
        await asyncio.sleep(delay_sec)
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        pass


@router.message(F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}))
async def filter_group_messages(message: types.Message, bot: Bot):
    chat_id = message.chat.id

    if message.sender_chat and message.sender.chat.id != chat_id:
        try:
            await message.delete()
            await send_temp_warning(
                bot,
                chat_id,
                f"⚠️ Channel messages are prohibited here. Post from your personal account.",
            )
            return
        except Exception as e:
            logger.error("Failed to delete channel impersonation message: %s", e)
            return

    user = message.from_user
    if not user or user.is_bot:
        return

    is_admin = await is_user_admin(bot, chat_id, user.id)
    if is_admin:
        return

    async with async_session_maker() as session:
        query = select(GroupSetting).where(GroupSetting.chat_id == chat_id)
        result = await session.execute(query)
        group = result.scalar_one_or_none()

    if not group or not group.is_active:
        return

    if group.anti_flood_enabled:
        flood_limit = group.anti_flood_limit or 5
        is_flooding = await check_flood_breach(
            chat_id=chat_id,
            user_id=user.id,
            max_messages=flood_limit,
            window_seconds=5,
        )

        if is_flooding:
            until_date = int(time.time() + MUTE_DURATION_SECONDS)
            user_name = user.first_name or "Member"

            try:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user.id,
                    permissions=RESTRICTED_PERMISSIONS,
                    until_date=until_date,
                )

                await message.delete()

                await send_temp_warning(
                    bot,
                    chat_id,
                    f"🚨 {user_name} has been muted for 15 minutes for flooding the chat.",
                    delay_sec=7,
                )
                logger.info("Muted user %s in chat %s for flooding", user.id, chat_id)
                return
            except Exception as e:
                logger.error("Failed to execute anti-flood mute on user %s: %s", user.id, e)
                return

    text = message.text or message.caption or ""

    entities = message.entities or message.caption_entities or []
    has_entity_link = any(
        entity.type in {"url", "text_link"} for entity in entities
    )


    if not group or not group.is_active:
        return

    if group.block_telegram_invites and (contains_telegram_invite(text) or has_entity_link):
        if contains_telegram_invite(text):
            try:
                await message.delete()
                user_name = user.first_name or "Member"
                await send_temp_warning(
                    bot,
                    chat_id,
                    f"⚠️ {user_name}, Telegram invite links are not permitted in this group. Please refrain from sharing them.",
                )
                return
            except Exception as e:
                logger.error("Failed to delete invite message: %s", e)
                return

    if group.block_all_links and (contains_link(text) or has_entity_link):
        try:
            await message.delete()
            user_name = user.first_name or "Member"
            await send_temp_warning(
                bot,
                chat_id,
                f"⚠️ {user_name}, sharing links is not allowed in this group. Please avoid posting them.",
            )
            return

        except Exception as e:
            logger.error("Failed to delete link message: %s", e)