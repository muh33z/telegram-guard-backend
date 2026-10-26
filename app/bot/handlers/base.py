import logging
from aiogram import Router, types
from aiogram.filters.chat_member_updated import (
    ADMINISTRATOR,
    IS_MEMBER,
    IS_NOT_MEMBER,
    ChatMemberUpdatedFilter,
)
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.group import GroupSetting

logger = logging.getLogger(__name__)
router = Router()

@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> (IS_MEMBER | ADMINISTRATOR))
)
async def on_bot_added_to_group(event: types.ChatMemberUpdated):
    chat = event.chat
    if chat.type not in ["group", "supergroup"]:
        return

    async with async_session_maker() as session:
        query = select(GroupSetting).where(GroupSetting.chat_id == chat.id)
        result = await session.execute(query)
        group = result.scalar_one_or_none()

        if not group:
            group = GroupSetting(
                chat_id=chat.id,
                title=chat.title or "Untitled Group",
                is_active=True,
            )
            session.add(group)
            logger.info("Registered new group: %s (%s)", chat.title, chat.id)
        else:
            group.is_active = True
            group.title = chat.title or group.title
            logger.info("Re-activated existing group: %s (%s)", chat.title, chat.id)

        await session.commit()

@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=(IS_MEMBER | ADMINISTRATOR) >> IS_NOT_MEMBER)
)
async def on_bot_removed_from_group(event: types.ChatMemberUpdated):
    chat = event.chat
    async with async_session_maker() as session:
        query = select(GroupSetting).where(GroupSetting.chat_id == chat.id)
        result = await session.execute(query)
        group = result.scalar_one_or_none()

        if group:
            group.is_active = False
            await session.commit()
            logger.info("Marked group as inactive: %s (%s)", chat.title, chat.id)