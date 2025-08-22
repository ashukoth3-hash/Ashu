import os, json, asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from telegram.error import Forbidden

# =============== CONFIG ===============
BOT_TOKEN = os.getenv("7573978624:AAGcZDx_q346W3ShSUirnX2voQaaGO7fjcE") or "7573978624:AAGcZDx_q346W3ShSUirnX2voQaaGO7fjcE" # Render ENV var
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# Force-join channels (WITHOUT @)
REQUIRED_CHANNELS = [
    "loot4udeal",
    "free_redeem_codes_fire_crypto",
    "crypto_free_redeem_codes_fire",
]

# Proof channel (OPEN LINK)
PROOF_CHANNEL_URL = "https://t.me/vipredeem"

# Admins (numeric Telegram user IDs)
ADMINS = {1898098929}

# Coins settings
SIGNUP_BONUS = 50
DAILY_BONUS = 10
REFER_BONUS = 100

# Withdraw slabs: [coins, label]
WITHDRAW_OPTIONS = [
    (2000, "2000 coins – ₹10"),
    (4000, "4000 coins – ₹20"),
    (8000, "8000 coins – ₹45"),
]

DB_FILE = "db.json"
db: Dict[str, Any] = {"users": {}}
DB_LOCK = asyncio.Lock()


# =============== DB HELPERS ===============
def load_db():
    global db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        db = {"users": {}}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_user(uid: int) -> Dict[str, Any]:
    uid = str(uid)
    if uid not in db["users"]:
        db["users"][uid] = {
            "coins": 0,
            "ref_by": None,
            "verified": False,
            "joined_bonus_done": False,
            "last_bonus_date": None,
            "refs": 0,
            "email": None,
        }
    return db["users"][uid]


# =============== UI ===============
def join_force_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Join 1", url=f"https://t.me/{REQUIRED_CHANNELS[0]}")],
        [InlineKeyboardButton("Join 2", url=f"https://t.me/{REQUIRED_CHANNELS[1]}")],
        [InlineKeyboardButton("Join 3", url=f"https://t.me/{REQUIRED_CHANNELS[2]}")],
        [InlineKeyboardButton("✅ Claim", callback_data="claim_join")],
    ]
    return InlineKeyboardMarkup(rows)

def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Refer", callback_data="refer")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("✉️ Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🧾 Proof", callback_data="proof")],
    ]
    return InlineKeyboardMarkup(rows)

def withdraw_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"wd_{coins}")]
            for coins, label in WITHDRAW_OPTIONS]
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# =============== FORCE JOIN CHECK ===============
async def is_joined_everywhere(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    bot = ctx.bot
    for ch in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(f"@{ch}", user_id)
            if m.status in ("left", "kicked"):
                return False
        except Forbidden:
            # if bot not admin / channel private etc., skip check to avoid hard block
            return False
        except Exception:
            return False
    return True


# =============== HANDLERS ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_db()
    user = update.effective_user
    u = get_user(user.id)

    # signup bonus (one-time)
    if not u["joined_bonus_done"]:
        u["coins"] += SIGNUP_BONUS
        u["joined_bonus_done"] = True
        save_db()

    text = (
        f"😍 Hey !! <b>{user.first_name}</b> Welcome To Bot\n"
        f"🟢 Must Join All Channels To Use Bot\n"
        f"⬛ After Joining click <b>Claim</b>"
    )
    await update.message.reply_html(text, reply_markup=join_force_kb())

async def claim_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if await is_joined_everywhere(context, user.id):
        await query.edit_message_text(
            f"✅ Welcome <b>{user.first_name}</b>\nChoose an option:",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await query.answer("Sab channels join karo pehle 🙂", show_alert=True)

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    u = get_user(user.id)
    text = (
        f"Hello 👋 <b>{user.first_name}</b>\n\n"
        f"APKA ABHI BALANCE H🤑 <b>{u['coins']}</b>\n\n"
        f"MINIMUM WITHDRAWAL 2000 COIN KA H"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu_kb())

async def show_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    link = f"https://t.me/{(await context.bot.get_me()).username}?start={user.id}"
    text = (
        f"Hello 👋 <b>{user.first_name}</b>\n"
        f"Apka Referral Link 👇\n{link}\n\n"
        f"Per refer = <b>{REFER_BONUS}</b> coin 🪙\n\n"
        f"🔴 Not Fake Refer Allowed"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu_kb())

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    u = get_user(user.id)

    ok = False
    today = datetime.utcnow().date()
    last = u["last_bonus_date"]
    if not last or datetime.fromisoformat(last).date() <= today - timedelta(days=1):
        u["coins"] += DAILY_BONUS
        u["last_bonus_date"] = datetime.utcnow().isoformat()
        save_db()
        ok = True

    msg = (f"Hello 👋 <b>{user.first_name}</b>\n"
           f"Daily bonus har 24 hours me add hota hai.\n"
           f"Aaj ka bonus: <b>+{DAILY_BONUS}</b> coins ✅") if ok else \
          ("⏳ Aapne aaj ka bonus le liya. Kal fir try karein 🙂")

    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=main_menu_kb())

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    u = get_user(user.id)
    text = (
        f"Hello 👋 <b>{user.first_name}</b>\n"
        f"Aapka balance: <b>{u['coins']}</b>\n\n"
        f"Withdrawal 1–2 hours me aapke <b>email</b> par aa jayega.\n"
        f"Amount choose karein:"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=withdraw_kb())

async def choose_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    u = get_user(user.id)

    coins = int(query.data.split("_")[1])
    if u["coins"] < coins:
        await query.answer("Itne coins nahi hain 😅", show_alert=True)
        return

    u["coins"] -= coins
    save_db()

    await query.edit_message_text(
        f"✅ Request placed for <b>{coins}</b> coins.\n"
        f"Payment 1–2 hours me email par aa jayega.",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )

async def proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Proofs yahan milenge:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📂 Open Proof Channel", url=PROOF_CHANNEL_URL)],
             [InlineKeyboardButton("◀️ Back", callback_data="back_menu")]]
        )
    )

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Choose an option:",
        reply_markup=main_menu_kb()
    )


# =============== ADMIN (NO CONVERSATION) ===============
def is_admin(uid: int) -> bool:
    return uid in ADMINS

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "Admin:\n"
        "/add <user_id> <coins>\n"
        "/deduct <user_id> <coins>\n"
        "/broadcast <text>"
    )

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    u = get_user(uid)
    u["coins"] += amount
    save_db()
    await update.message.reply_text(f"✅ Added {amount} coins to {uid} (total {u['coins']})")

async def deduct_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("Usage: /deduct <user_id> <coins>")
        return
    u = get_user(uid)
    u["coins"] = max(0, u["coins"] - amount)
    save_db()
    await update.message.reply_text(f"✅ Deducted {amount} coins from {uid} (total {u['coins']})")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <text>")
        return
    text = " ".join(context.args)
    ok = 0
    for uid in list(db["users"].keys()):
        try:
            await context.bot.send_message(int(uid), text)
            ok += 1
        except Exception:
            pass
    await update.message.reply_text(f"📣 Sent to {ok} users.")


# =============== ENTRY POINT ===============
def main():
    load_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("deduct", deduct_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # Buttons
    app.add_handler(CallbackQueryHandler(claim_join, pattern="^claim_join$"))
    app.add_handler(CallbackQueryHandler(show_balance, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(show_refer, pattern="^refer$"))
    app.add_handler(CallbackQueryHandler(daily_bonus, pattern="^daily_bonus$"))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(choose_withdraw, pattern="^wd_"))
    app.add_handler(CallbackQueryHandler(proof, pattern="^proof$"))
    app.add_handler(CallbackQueryHandler(back_menu, pattern="^back_menu$"))

    print("🤖 Bot started…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
