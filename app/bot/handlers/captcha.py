import asyncio
import logging
import random
from aiogram import Bot, F, Router, types
from aiogram.filters.chat_member_updated import (
    IS_MEMBER,
    IS_NOT_MEMBER,
    ChatMemberUpdatedFilter
)
from aiogram.types import ChatPermissions
from sqlalchemy import select

from app.bot.keyboards.captcha_kb import build_captcha_keyboard
from app.core.database import async_session_maker
from app.core.redis import redis_client
from app.models.group import GroupSetting

from app.bot.utils.permissions import RESTRICTED_PERMISSIONS, UNRESTRICTED_PERMISSIONS

logger = logging.getLogger(__name__)
router = Router()


async def auto_kick_unverified_user(
    bot: Bot,
    chat_id: int,
    user_id: int,
    message_id: int,
    timeout_sec: int
):
    await asyncio.sleep(timeout_sec)

    redis_key = f"captcha:{chat_id}:{user_id}"
    if await redis_client.exists(redis_key):
        await redis_client.delete(redis_key)
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info("Auto-kicked unverified user %s from chat %s", user_id, chat_id)
        except Exception as e:
            logger.error("Failed to kick unverified user %s: %s", user_id, e)

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(event: types.ChatMemberUpdated, bot: Bot):
    chat = event.chat
    new_member = event.new_chat_member.user

    if new_member.is_bot:
        return

    async with async_session_maker() as session:
        query = select(GroupSetting).where(GroupSetting.chat_id == chat.id)
        result = await session.execute(query)
        group = result.scalar_one_or_none()

    if not group or not group.captcha_enabled:
        return

    timeout = group.captcha_timeout_sec or 60

    try:
        await bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=new_member.id,
            permissions=RESTRICTED_PERMISSIONS,
        )

        num1, num2 = random.randint(1, 9), random.randint(1, 9)
        answer = num1 + num2

        keyboard = build_captcha_keyboard(user_id=new_member.id, correct_answer=answer)
        user_name = new_member.first_name or "New Member"

        prompt_msg = await bot.send_message(
            chat_id=chat.id,
            text=(
                f"Welcome, [{user_name}](tg://user?id={new_member.id})!\n"
                f"To speak in this group, please verify your are human within {timeout} seconds.\n\n"
                f"**What is {num1} + {num2}?**"
            ),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        redis_key = f"captcha:{chat.id}:{new_member.id}"
        await redis_client.set(redis_key, str(answer), ex=timeout)

        asyncio.create_task(
            auto_kick_unverified_user(
                bot=bot,
                chat_id=chat.id,
                user_id=new_member.id,
                message_id=prompt_msg.message_id,
                timeout_sec=timeout,
            )
        )

    except Exception as e:
        logger.error("Failed to execute CAPTCHA gatekeeper for %s: %s", new_member.id, e)

@router.callback_query(F.data.startswith("captcha:"))
async def on_captcha_callback(callback: types.CallbackQuery, bot: Bot):
    _, target_user_id, is_correct_str = callback.data.split(":")
    target_user_id = int(target_user_id)
    is_correct = is_correct_str == "1"

    if callback.from_user.id != target_user_id:
        await callback.answer("This verification is not for you.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    redis_key = f"captcha:{chat_id}:{target_user_id}"

    if not await redis_client.exists(redis_key):
        await callback.answer("Verification expired or already solved.", show_alert=True)
        return

    await redis_client.delete(redis_key)

    if is_correct:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=UNRESTRICTED_PERMISSIONS,
        )
        await callback.answer("Verification successful! You can now chat.")

        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("Incorrect answer. You have been removed.", show_alert=True)
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
            await bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
            await callback.message.delete()
        except Exception as e:
            logger.error("Failed to kick user upon incorrect CAPTCHA: %s", e)