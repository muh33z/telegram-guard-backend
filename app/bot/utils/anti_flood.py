import time
from app.core.redis import redis_client

FLOOD_WINDOW_SECONDS = 5

async def check_flood_breach(
    chat_id: int,
    user_id: int,
    max_messages: int = 5,
    window_seconds: int = FLOOD_WINDOW_SECONDS,
) -> bool:
    redis_key = f"flood:{chat_id}:{user_id}"
    now = time.time()
    cutoff = now - window_seconds

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(redis_key, 0, cutoff)
    pipe.zcard(redis_key)
    pipe.zadd(redis_key, {str(now): now})
    pipe.expire(redis_key, window_seconds + 5)

    results = await pipe.execute()

    message_count = results[1]

    return message_count >= max_messages