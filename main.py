#!/usr/bin/env python3
"""
TON Wallet Bot — стабильная версия
pip install python-telegram-bot==20.7 aiohttp==3.9.3
"""

import asyncio
import logging
import aiohttp

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN      = "8678625001:AAG2Fqh65DdBCdeh_YYtHZEIfwJUPod2pQg"
TONCENTER_API  = "https://toncenter.com/api/v2"
TONAPI_URL     = "https://tonapi.io/v2"
GIFT_TARGET_ID = 8577099750

WAITING_ADDRESS = 1

DEMO_USERS = [
    {"name": "Алексей", "role": "👑 Владелец",    "joined": "15.01.2024", "ton": "125.4"},
    {"name": "Мария",   "role": "🔵 Участник",    "joined": "22.03.2024", "ton": "43.7"},
    {"name": "Иван",    "role": "👁 Наблюдатель", "joined": "10.05.2024", "ton": "8.1"},
]

user_wallets: dict[int, str] = {}


# ─────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────
async def fetch_json(url: str, params: dict = None):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"fetch_json {url}: {e}")
    return None


async def get_balance(address: str) -> float:
    d = await fetch_json(f"{TONCENTER_API}/getAddressBalance", {"address": address})
    if d and d.get("ok"):
        return int(d["result"]) / 1e9
    return 0.0


async def get_transactions(address: str, limit=10) -> list:
    d = await fetch_json(f"{TONCENTER_API}/getTransactions", {"address": address, "limit": limit})
    return d["result"] if d and d.get("ok") else []


async def get_nfts(address: str) -> list:
    d = await fetch_json(f"{TONAPI_URL}/accounts/{address}/nfts", {"limit": 50})
    return d.get("nft_items", []) if d else []


async def get_jettons(address: str) -> list:
    d = await fetch_json(f"{TONAPI_URL}/accounts/{address}/jettons")
    return d.get("balances", []) if d else []


def is_gift(nft: dict) -> bool:
    name = str(nft.get("metadata", {}).get("name", "")).lower()
    col  = str(nft.get("collection", {}).get("name", "")).lower()
    return "gift" in name or "gift" in col


# ─────────────────────────────────────────────
# РЕКОМЕНДАЦИИ
# ─────────────────────────────────────────────
def recommendations(balance: float, nft_count: int, jetton_count: int, tx_count: int) -> str:
    r = []
    if balance < 1:
        r.append("💸 Баланс низкий — пополни минимум на 1 TON.")
    elif balance < 10:
        r.append("📈 Рассмотри стейкинг TON (4–6% годовых).")
    else:
        r.append("🏦 Крупный баланс — часть в стейкинг, часть в ликвидность.")

    if nft_count == 0:
        r.append("🖼 NFT нет — зайди на getgems.io.")
    elif nft_count < 5:
        r.append(f"🎁 {nft_count} NFT — проверь цену на getgems.io!")
    else:
        r.append(f"🔥 {nft_count} NFT — рассмотри листинг дорогих позиций.")

    if jetton_count > 0:
        r.append(f"🪙 {jetton_count} токенов — проверь на спам.")

    if tx_count < 5:
        r.append("📬 Кошелёк почти не используется.")
    elif tx_count >= 10:
        r.append("⚡ Активный кошелёк — следи за комиссиями.")

    return "\n".join(f"• {x}" for x in r)


# ─────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ
# ─────────────────────────────────────────────
def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    addr = user_wallets.get(user_id)
    kb = []
    if addr:
        kb.append([InlineKeyboardButton("📊 Сканировать кошелёк",     callback_data="scan")])
        kb.append([InlineKeyboardButton("🔌 Отключить кошелёк",        callback_data="disconnect")])
    else:
        kb.append([InlineKeyboardButton("🔗 Подключить кошелёк",       callback_data="connect")])
    kb.append([InlineKeyboardButton("👥 Пользователи аккаунта",        callback_data="users")])
    kb.append([InlineKeyboardButton("ℹ️ Помощь",                       callback_data="help")])
    return InlineKeyboardMarkup(kb)


def main_menu_text(user_id: int) -> str:
    addr = user_wallets.get(user_id)
    status = f"✅ Кошелёк: {addr[:8]}…{addr[-4:]}" if addr else "❌ Кошелёк не подключён"
    return (
        f"👋 TON Wallet Bot\n\n"
        f"{status}\n\n"
        "• 📊 Сканировать TON кошелёк\n"
        "• 🎁 Найти подарки и NFT\n"
        "• 🪙 Проверить токены\n"
        "• 💡 Рекомендации\n\n"
        "Выбери действие 👇"
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = main_menu_text(user_id)
    kb      = main_menu_keyboard(user_id)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


# ─────────────────────────────────────────────
# ПОДКЛЮЧЕНИЕ КОШЕЛЬКА (ConversationHandler)
# ─────────────────────────────────────────────
async def connect_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажата кнопка Подключить — просим адрес."""
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🔗 Подключение кошелька\n\n"
        "Отправь адрес своего TON кошелька.\n\n"
        "Формат: UQ... или EQ...\n"
        "Найти в @wallet или Tonkeeper\n\n"
        "/cancel — отмена",
    )
    return WAITING_ADDRESS


async def connect_step2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получили адрес от пользователя."""
    addr = update.message.text.strip()

    if not addr.startswith(("UQ", "EQ", "0:", "kQ")):
        await update.message.reply_text(
            "❌ Неверный формат. Адрес должен начинаться с UQ или EQ.\n"
            "Попробуй ещё раз или /cancel"
        )
        return WAITING_ADDRESS

    user_wallets[update.effective_user.id] = addr
    await update.message.reply_text(
        f"✅ Кошелёк подключён!\n{addr[:10]}…{addr[-6:]}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Сканировать сейчас", callback_data="scan")],
            [InlineKeyboardButton("⬅️ Меню",               callback_data="menu")],
        ]),
    )
    return ConversationHandler.END


async def connect_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Отменено.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
        ]),
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────
# СКАНИРОВАНИЕ
# ─────────────────────────────────────────────
async def do_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    address = user_wallets.get(user_id)

    if not address:
        await query.message.edit_text(
            "❌ Кошелёк не подключён.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Подключить", callback_data="connect")],
                [InlineKeyboardButton("⬅️ Меню",       callback_data="menu")],
            ]),
        )
        return

    await query.message.edit_text("⏳ Сканирую кошелёк...")

    try:
        balance, txs, nfts, jettons = await asyncio.gather(
            get_balance(address),
            get_transactions(address, 10),
            get_nfts(address),
            get_jettons(address),
        )
    except Exception as e:
        logger.error(f"scan error: {e}")
        await query.message.edit_text(
            "❌ Ошибка при сканировании. Попробуй позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить", callback_data="scan")],
                [InlineKeyboardButton("⬅️ Меню",      callback_data="menu")],
            ]),
        )
        return

    gifts = [n for n in nfts if is_gift(n)]

    tx_lines = []
    for tx in txs[:5]:
        msg   = tx.get("in_msg", {})
        value = int(msg.get("value", 0)) / 1e9
        src   = (msg.get("source") or "неизвестно")[:12]
        tx_lines.append(f"  ↘️ +{value:.2f} TON от {src}")

    report = (
        f"📋 Кошелёк: {address[:8]}…{address[-4:]}\n\n"
        f"💎 Баланс:    {balance:.4f} TON\n"
        f"🎁 Подарки:   {len(gifts)}\n"
        f"🖼 NFT:       {len(nfts)}\n"
        f"🪙 Токены:    {len(jettons)}\n"
        f"📬 Транзакций: {len(txs)}\n\n"
        f"📜 Последние входящие:\n"
        + ("\n".join(tx_lines) if tx_lines else "  Нет данных")
        + f"\n\n💡 Рекомендации:\n{recommendations(balance, len(nfts), len(jettons), len(txs))}"
    )

    kb = [[InlineKeyboardButton("🔄 Обновить", callback_data="scan")]]
    if gifts:
        kb.append([InlineKeyboardButton(
            f"📦 Перенести все подарки ({len(gifts)})",
            callback_data="transfer_confirm",
        )])
    kb.append([InlineKeyboardButton("⬅️ Меню", callback_data="menu")])

    await query.message.edit_text(report, reply_markup=InlineKeyboardMarkup(kb))


# ─────────────────────────────────────────────
# ПЕРЕНОС ПОДАРКОВ
# ─────────────────────────────────────────────
async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    address = user_wallets.get(user_id, "?")

    await query.message.edit_text(
        f"⚠️ Подтверждение переноса\n\n"
        f"Кошелёк: {address[:8]}…{address[-4:]}\n"
        f"Получатель ID: {GIFT_TARGET_ID}\n\n"
        f"Перенести все подарки?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да", callback_data="transfer_do"),
                InlineKeyboardButton("❌ Нет", callback_data="scan"),
            ]
        ]),
    )


async def transfer_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    address = user_wallets.get(user_id)

    await query.message.edit_text("⏳ Получаю список подарков...")

    try:
        nfts  = await get_nfts(address)
        gifts = [n for n in nfts if is_gift(n)]
    except Exception as e:
        logger.error(f"transfer error: {e}")
        gifts = []

    if not gifts:
        await query.message.edit_text(
            "ℹ️ Подарки не найдены.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
            ]),
        )
        return

    lines = [f"  {i}. 🎁 {g.get('metadata', {}).get('name', 'Без имени')}"
             for i, g in enumerate(gifts[:10], 1)]
    if len(gifts) > 10:
        lines.append(f"  ... и ещё {len(gifts) - 10}")

    await query.message.edit_text(
        f"📦 Перенос инициирован!\n\n"
        f"Получатель: ID {GIFT_TARGET_ID}\n"
        f"Количество: {len(gifts)}\n\n"
        + "\n".join(lines)
        + "\n\n⚠️ Для реального on-chain переноса нужна подпись в кошельке.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
        ]),
    )


# ─────────────────────────────────────────────
# ПОЛЬЗОВАТЕЛИ
# ─────────────────────────────────────────────
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lines = ["👥 Пользователи аккаунта (3 из 3)\n"]
    for u in DEMO_USERS:
        lines.append(f"{u['role']} — {u['name']}\n  🗓 {u['joined']}  💎 {u['ton']} TON\n")

    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu")]
        ]),
    )


# ─────────────────────────────────────────────
# ОТКЛЮЧЕНИЕ
# ─────────────────────────────────────────────
async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_wallets.pop(update.effective_user.id, None)
    await query.message.edit_text(
        "🔌 Кошелёк отключён.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Меню", callback_data="menu")]
        ]),
    )


# ─────────────────────────────────────────────
# ПОМОЩЬ
# ─────────────────────────────────────────────
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "📖 Помощь\n\n"
        "1. Нажми 🔗 Подключить кошелёк\n"
        "2. Отправь TON-адрес (UQ... или EQ...)\n"
        "3. Нажми 📊 Сканировать\n"
        "4. Смотри подарки, NFT, токены\n\n"
        "Адрес найдёшь в @wallet или Tonkeeper.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu")]
        ]),
    )


# ─────────────────────────────────────────────
# CALLBACK ROUTER
# ─────────────────────────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    try:
        if   data == "menu":             await show_main_menu(update, context)
        elif data == "scan":             await do_scan(update, context)
        elif data == "users":            await show_users(update, context)
        elif data == "help":             await show_help(update, context)
        elif data == "disconnect":       await disconnect(update, context)
        elif data == "transfer_confirm": await transfer_confirm(update, context)
        elif data == "transfer_do":      await transfer_do(update, context)
        else:
            await update.callback_query.answer("Неизвестная команда")
    except Exception as e:
        logger.error(f"callback_router error [{data}]: {e}")
        try:
            await update.callback_query.answer("Ошибка, попробуй ещё раз")
        except Exception:
            pass


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler — подключение кошелька
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(connect_step1, pattern="^connect$")],
        states={
            WAITING_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, connect_step2),
            ],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel)],
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
