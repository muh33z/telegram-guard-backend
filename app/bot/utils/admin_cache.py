import logging
from aiogram import Bot
from app.core.redis import redis_client

logger = logging.getLogger(__name__)
ADMIN_CACHE_TTL = 300

async def is_user_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    redis_key = f"admins:{chat_id}"

    if await redis_client.exists(redis_key):
        return bool(await redis_client.sismember(redis_key, str(user_id)))

    try:
        admins = await bot.get_chat_administrators(chat_id=chat_id)
        admin_ids = [str(admin.user.id) for admin in admins]

        if admin_ids:
            await redis_client.sadd(redis_key, *admin_ids)
            await redis_client.expire(redis_key, ADMIN_CACHE_TTL)

        return str(user_id) in admin_ids
    except Exception as e:
        logger.error("Failed to fetch administrators for chat %s: %s", chat_id, e)
        return False

async def invalidate_admin_cache(chat_id: int):
    await redis_client.delete(f"admins:{chat_id}")