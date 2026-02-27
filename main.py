#!/usr/bin/env python3
"""
TON Wallet Telegram Bot
Сканирует TON кошелёк, подарки, NFT и даёт рекомендации.
Требования: pip install python-telegram-bot aiohttp
"""

import asyncio
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import aiohttp

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN = "8678625001:AAG2Fqh65DdBCdeh_YYtHZEIfwJUPod2pQg"          # Вставь свой токен
TONCENTER_API = "https://toncenter.com/api/v2"
TONAPI_URL    = "https://tonapi.io/v2"

# Демо: 3 пользователя на аккаунте (как просили показать)
DEMO_USERS = [
    {"id": 1, "name": "Алексей", "role": "👑 Владелец",    "joined": "15.01.2024", "ton": "125.4"},
    {"id": 2, "name": "Мария",   "role": "🔵 Участник",    "joined": "22.03.2024", "ton": "43.7"},
    {"id": 3, "name": "Иван",    "role": "👁 Наблюдатель", "joined": "10.05.2024", "ton": "8.1"},
]

# Хранилище адресов пользователей (in-memory)
user_wallets: dict[int, str] = {}


# ─────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────
async def fetch_json(url: str, params: dict = None) -> dict | None:
    """Универсальный GET-запрос с возвратом JSON."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Ошибка запроса {url}: {e}")
    return None


async def get_ton_balance(address: str) -> float:
    """Возвращает баланс в TON."""
    data = await fetch_json(f"{TONCENTER_API}/getAddressBalance", {"address": address})
    if data and data.get("ok"):
        return int(data["result"]) / 1e9
    return 0.0


async def get_wallet_info(address: str) -> dict:
    """Полная информация о кошельке через TonCenter."""
    data = await fetch_json(f"{TONCENTER_API}/getAddressInformation", {"address": address})
    if data and data.get("ok"):
        return data["result"]
    return {}


async def get_transactions(address: str, limit: int = 10) -> list:
    """Последние транзакции кошелька."""
    data = await fetch_json(
        f"{TONCENTER_API}/getTransactions",
        {"address": address, "limit": limit},
    )
    if data and data.get("ok"):
        return data["result"]
    return []


async def get_nft_items(address: str) -> list:
    """NFT и подарки через TonAPI."""
    data = await fetch_json(f"{TONAPI_URL}/accounts/{address}/nfts", {"limit": 50})
    if data:
        return data.get("nft_items", [])
    return []


async def get_jettons(address: str) -> list:
    """Jetton (токены) на кошельке."""
    data = await fetch_json(f"{TONAPI_URL}/accounts/{address}/jettons")
    if data:
        return data.get("balances", [])
    return []


# ─────────────────────────────────────────────
# РЕКОМЕНДАЦИИ
# ─────────────────────────────────────────────
def generate_recommendations(balance: float, nft_count: int, jetton_count: int, tx_count: int) -> str:
    recs = []

    if balance < 1:
        recs.append("💸 Баланс низкий — пополни кошелёк минимум на 1 TON для комфортной работы.")
    elif balance < 10:
        recs.append("📊 Хороший старт! Рассмотри стейкинг TON для пассивного дохода (4-6% годовых).")
    else:
        recs.append("🏦 Крупный баланс. Диверсифицируй: часть в стейкинг, часть в ликвидность.")

    if nft_count == 0:
        recs.append("🖼 NFT не найдено. Рынок TON активен — зайди на getgems.io.")
    elif nft_count < 5:
        recs.append(f"🎁 У тебя {nft_count} NFT/подарков. Проверь их цену на getgems.io — вдруг вырос флор!")
    else:
        recs.append(f"🔥 {nft_count} NFT — серьёзная коллекция! Рассмотри листинг дорогих позиций.")

    if jetton_count > 0:
        recs.append(f"🪙 Найдено {jetton_count} токенов. Проверь их актуальность — часть может быть спам.")

    if tx_count < 5:
        recs.append("📬 Мало транзакций — кошелёк почти не используется.")
    elif tx_count >= 10:
        recs.append("⚡ Активный кошелёк. Следи за комиссиями при пиковых нагрузках сети.")

    return "\n".join(f"  • {r}" for r in recs)


# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔗 Подключить кошелёк", callback_data="connect_wallet")],
        [InlineKeyboardButton("👥 Пользователи аккаунта", callback_data="show_users")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
    ]
    await update.message.reply_text(
        "👋 *TON Wallet Bot*\n\n"
        "Я помогу тебе:\n"
        "• 📊 Просканировать TON кошелёк\n"
        "• 🎁 Найти подарки и NFT\n"
        "• 🪙 Проверить токены (Jettons)\n"
        "• 💡 Дать персональные рекомендации\n\n"
        "Выбери действие ниже 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /scan <адрес> — ручной ввод адреса."""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        # Если адрес уже сохранён
        address = user_wallets.get(user_id)
        if not address:
            await update.message.reply_text(
                "❗ Укажи адрес кошелька:\n`/scan UQ...`",
                parse_mode="Markdown",
            )
            return
    else:
        address = args[0]
        user_wallets[user_id] = address

    await scan_wallet(update, address)


async def scan_wallet(update: Update, address: str):
    """Основная логика сканирования."""
    msg = await update.effective_message.reply_text("⏳ Сканирую кошелёк...")

    # Параллельные запросы
    balance, transactions, nfts, jettons = await asyncio.gather(
        get_ton_balance(address),
        get_transactions(address, 10),
        get_nft_items(address),
        get_jettons(address),
    )

    nft_count   = len(nfts)
    jetton_count = len(jettons)
    tx_count    = len(transactions)

    # Подарки = NFT с именем "Gift" или "Telegram Gift"
    gifts = [
        n for n in nfts
        if "gift" in str(n.get("metadata", {}).get("name", "")).lower()
        or "gift" in str(n.get("collection", {}).get("name", "")).lower()
    ]

    # Последние транзакции
    tx_lines = []
    for tx in transactions[:5]:
        in_msg  = tx.get("in_msg", {})
        value   = int(in_msg.get("value", 0)) / 1e9
        source  = in_msg.get("source", "неизвестно")[:10]
        tx_lines.append(f"  ↘️ +{value:.2f} TON от {source}…")

    tx_text = "\n".join(tx_lines) if tx_lines else "  Нет данных"

    recs = generate_recommendations(balance, nft_count, jetton_count, tx_count)

    report = (
        f"📋 *Отчёт по кошельку*\n"
        f"`{address[:10]}…{address[-6:]}`\n\n"
        f"💎 *Баланс:* `{balance:.4f} TON`\n"
        f"🎁 *Подарки:* `{len(gifts)}`\n"
        f"🖼 *Всего NFT:* `{nft_count}`\n"
        f"🪙 *Токены (Jettons):* `{jetton_count}`\n"
        f"📬 *Транзакций (10):* `{tx_count}`\n\n"
        f"📜 *Последние входящие:*\n{tx_text}\n\n"
        f"💡 *Рекомендации:*\n{recs}"
    )

    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data=f"rescan_{address}")]]
    await msg.edit_text(report, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать 3 пользователей аккаунта."""
    lines = ["👥 *Пользователи аккаунта* (3 из 3)\n"]
    for u in DEMO_USERS:
        lines.append(
            f"{u['role']} *{u['name']}*\n"
            f"  🗓 Вступил: {u['joined']}\n"
            f"  💎 Баланс: {u['ton']} TON\n"
        )
    text = "\n".join(lines)
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "connect_wallet":
        await query.message.reply_text(
            "🔗 *Подключение кошелька*\n\n"
            "Отправь адрес своего TON кошелька командой:\n"
            "`/scan UQxxxx...`\n\n"
            "Адрес можно найти в @wallet или Tonkeeper.",
            parse_mode="Markdown",
        )

    elif data == "show_users":
        await show_users(update, context)

    elif data == "help":
        await query.message.reply_text(
            "📖 *Помощь*\n\n"
            "/start — главное меню\n"
            "/scan <адрес> — сканировать кошелёк\n"
            "/users — показать пользователей\n\n"
            "Поддерживаемые форматы адресов:\n"
            "• UQ... (user-friendly)\n"
            "• EQ... (bounceable)",
            parse_mode="Markdown",
        )

    elif data == "back_main":
        await cmd_start(update, context)

    elif data.startswith("rescan_"):
        address = data.split("rescan_", 1)[1]
        await scan_wallet(update, address)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Если пользователь просто отправил адрес текстом."""
    text = update.message.text.strip()
    if text.startswith(("UQ", "EQ", "0:", "kQ")):
        user_wallets[update.effective_user.id] = text
        await scan_wallet(update, text)
    else:
        await update.message.reply_text(
            "❓ Не понял. Отправь TON-адрес или используй /start"
        )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_users(update, context)


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("scan",   cmd_scan))
    app.add_handler(CommandHandler("users",  cmd_users))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
