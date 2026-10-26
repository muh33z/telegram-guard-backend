import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request, status
from aiogram import Bot, Dispatcher, types
from app.core.config import settings
from app.core.database import Base, engine
from app.bot.handlers import base, captcha

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

dp.include_router(base.router)
dp.include_router(captcha.router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    webhook_url = f"{settings.BASE_WEBHOOK_URL}/api/webhook"
    logger.info("Configuring Telegram webhook to %s", webhook_url)
    
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET,
        allowed_updates=["message", "chat_member", "my_chat_member", "callback_query"],
        drop_pending_updates=True,
    )
    yield
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)

@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid secret token",
        )

    data = await request.json()
    update = types.Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}