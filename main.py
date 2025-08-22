import os, json, asyncio, re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import Forbidden

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU") or "7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU"
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set (Render Environment Variable me set karo)")

# Join-force channel usernames (WITHOUT @)
REQUIRED_CHANNELS = [
    "free_redeem_codes_fire_crypto",
    "loot4udeal",
]

# Proof/withdraw review channel (username or numeric id)
PROOF_CHANNEL = "@Withdrawal_Proofsj"       # <- apna proof/review channel laga दो (bot ko is channel me add karo)

# Admin IDs (comma separated if more)
ADMINS = [1898098929]                        # <- tumhara admin id

# Coins
SIGNUP_BONUS = 50
DAILY_BONUS  = 10
REFER_COIN   = 100

# Withdraw slabs (coins -> label)
WITHDRAW_OPTIONS: List[Tuple[int, str]] = [
    (2000, "₹10"),
    (4000, "₹20"),
    (6000, "₹30"),
]

DB_FILE = "db.json"
DB_LOCK = asyncio.Lock()
db: Dict[str, Any] = {"users": {}}

# --------- DB HELPERS ---------
def load_db():
    global db
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
        else:
            db = {"users": {}}
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
            "pending_withdraw": None,  # {"amount": coins, "label": "₹10"}
        }
    return db["users"][uid]

# --------- UI ----------
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 Balance", callback_data="bal"),
         InlineKeyboardButton("👥 Refer", callback_data="refer")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily"),
         InlineKeyboardButton("💸 Withdraw", callback_data="wd")],
        [InlineKeyboardButton("🧾 Proof", callback_data="proof")]
    ]
    return InlineKeyboardMarkup(rows)

def join_force_kb() -> InlineKeyboardMarkup:
    btns = []
    if len(REQUIRED_CHANNELS) >= 1:
        btns.append(InlineKeyboardButton("Join 1 ➡️", url=f"https://t.me/{REQUIRED_CHANNELS[0]}"))
    if len(REQUIRED_CHANNELS) >= 2:
        btns.append(InlineKeyboardButton("Join 2 ➡️", url=f"https://t.me/{REQUIRED_CHANNELS[1]}"))
    rows = [btns, [InlineKeyboardButton("✅ Claim", callback_data="claim_join")]]
    return InlineKeyboardMarkup(rows)

WELCOME_TEXT = (
    "🎉 Swagat hai!\n"
    "📌 Refer karo, coins banao — aur redeem codes withdraw karo!\n\n"
    f"🎁 Signup Bonus: {SIGNUP_BONUS} coins\n"
    f"🎁 Daily Bonus: {DAILY_BONUS} coins\n"
    f"👥 Per Refer: {REFER_COIN} coins"
)

# --------- HELPERS ----------
async def is_joined_everywhere(app: Application, uid: int) -> bool:
    member_ok = True
    for ch in REQUIRED_CHANNELS:
        try:
            mem = await app.bot.get_chat_member(chat_id=f"@{ch}", user_id=uid)
            if mem.status in ("left", "kicked"):
                member_ok = False
                break
        except Forbidden:
            # bot not admin / not present — treat as False so you’ll notice misconfig
            member_ok = False
            break
        except Exception:
            member_ok = False
            break
    return member_ok

# --------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args or []

    # attach referral if present
    async with DB_LOCK:
        u = get_user(uid)
        if args:
            ref = args[0]
            if ref.isdigit() and int(ref) != uid and u.get("ref_by") is None:
                u["ref_by"] = int(ref)
                save_db()

    # If not verified, show join-force panel first
    async with DB_LOCK:
        verified = get_user(uid).get("verified", False)

    if not verified:
        txt = (
            "😍 **Hey !! User Welcome To Bot**\n"
            "🟢 **Must Join All Channels To Use Bot**\n"
            "⬛ **After Joining click Claim**"
        )
        await update.message.reply_text(
            txt, reply_markup=join_force_kb(), parse_mode="Markdown"
        )
        return

    await update.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb())

# --------- CALLBACKS ----------
async def claim_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    app = context.application

    ok = await is_joined_everywhere(app, uid)

    async with DB_LOCK:
        u = get_user(uid)
        already = u.get("verified", False)
        if ok and not already:
            u["verified"] = True
            u["coins"] += SIGNUP_BONUS
            # credit refer bonus
            if u.get("ref_by"):
                ref_u = get_user(u["ref_by"])
                ref_u["coins"] += REFER_COIN
                ref_u["refs"] += 1
            save_db()

    if ok:
        await query.edit_message_text("✅ Verified! Signup bonus added.", reply_markup=main_menu_kb())
    else:
        await query.edit_message_text(
            "❌ Abhi sabhi channels join nahi mile. Pehle join karo, phir **Claim** dabao.",
            reply_markup=join_force_kb(), parse_mode="Markdown"
        )

async def on_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    async with DB_LOCK:
        coins = get_user(uid)["coins"]
    await query.edit_message_text(f"💰 Balance: **{coins}** coins", parse_mode="Markdown", reply_markup=main_menu_kb())

async def on_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_username = (await context.bot.get_me()).username
    uid = query.from_user.id
    link = f"https://t.me/{bot_username}?start={uid}"
    text = f"👥 Refer Link:\n`{link}`\n\nHar successful join = **{REFER_COIN}** coins."
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())

async def on_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    async with DB_LOCK:
        u = get_user(uid)
        now = datetime.utcnow().date().isoformat()
        if u.get("last_bonus_date") == now:
            msg = "⏳ Aaj ka daily bonus already claim ho chuka hai."
        else:
            u["last_bonus_date"] = now
            u["coins"] += DAILY_BONUS
            save_db()
            msg = f"🎁 Daily bonus added: **{DAILY_BONUS}** coins."

    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_menu_kb())

def withdraw_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for c, label in WITHDRAW_OPTIONS:
        rows.append([InlineKeyboardButton(f"{label} ({c} coins)", callback_data=f"wd_choose:{c}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)

async def on_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💸 Withdraw options choose karo:", reply_markup=withdraw_keyboard()
    )

async def wd_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    coins_needed = int(data[1])
    uid = query.from_user.id

    async with DB_LOCK:
        u = get_user(uid)
        bal = u["coins"]
        if bal < coins_needed:
            await query.edit_message_text(
                f"❌ Insufficient balance. Required: {coins_needed}, Your: {bal}",
                reply_markup=main_menu_kb()
            )
            return
        # mark pending; ask for UPI/Email
        u["pending_withdraw"] = {"amount": coins_needed, "label": next((lb for c, lb in WITHDRAW_OPTIONS if c==coins_needed), "N/A")}
        save_db()

    await query.edit_message_text(
        "📧 Apna email/UPI bhejo (1 line me).\n\nExample: `user@upi` ya `name@gmail.com`",
        parse_mode="Markdown"
    )
    # next message captured by message handler expecting details

EMAIL_RGX = re.compile(r"(^.+@.+\..+$)|(^\w+@\w+$)")

async def wd_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    uid = update.effective_user.id
    text = (update.message.text or "").strip()

    async with DB_LOCK:
        u = get_user(uid)
        pending = u.get("pending_withdraw")
        if not pending:
            return  # no active flow
        if not EMAIL_RGX.match(text):
            await update.message.reply_text("⚠️ Valid email/UPI format bhejo.")
            return
        # freeze coins and send review to PROOF_CHANNEL
        amount = pending["amount"]
        label = pending["label"]
        if u["coins"] < amount:
            await update.message.reply_text("❌ Balance change ho gaya hai; insufficient coins.")
            u["pending_withdraw"] = None
            save_db()
            return
        u["coins"] -= amount
        u["pending_withdraw"] = None
        u["email"] = text
        save_db()

    # send for admin review
    try:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"wd_ok:{uid}:{amount}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"wd_no:{uid}:{amount}")]
        ])
        msg = (f"🧾 *Withdraw Request*\n"
               f"User: `{uid}`\nAmount: *{label}* ({amount} coins)\n"
               f"Email/UPI: `{text}`\n\n/ban_{uid} (optional)")
        await context.bot.send_message(PROOF_CHANNEL, msg, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        pass

    await update.message.reply_text("✅ Request received. Admin review ke baad credit hoga.")

# Admin actions
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in ADMINS:
            if update.callback_query:
                await update.callback_query.answer("Admins only", show_alert=True)
            else:
                await update.message.reply_text("Admins only.")
            return
        return await func(update, context)
    return wrapper

@admin_only
async def wd_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid, amount = q.data.split(":")
    uid = int(uid)
    await q.edit_message_reply_markup(None)
    try:
        await context.bot.send_message(uid, "✅ Withdraw approved. Jaldi hi process hoga.")
    except Exception:
        pass

@admin_only
async def wd_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, uid, amount = q.data.split(":")
    uid = int(uid)

    # refund coins
    async with DB_LOCK:
        u = get_user(uid)
        u["coins"] += int(amount)
        save_db()

    await q.edit_message_reply_markup(None)
    try:
        await context.bot.send_message(uid, "❌ Withdraw rejected. Coins refund kar diye gaye.")
    except Exception:
        pass

# back button
async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu_kb())

# --------- ROUTER ----------
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data == "claim_join":
        return await claim_join(update, context)
    if data == "bal":
        return await on_balance(update, context)
    if data == "refer":
        return await on_refer(update, context)
    if data == "daily":
        return await on_daily_bonus(update, context)
    if data == "wd":
        return await on_withdraw(update, context)
    if data.startswith("wd_choose:"):
        return await wd_choose(update, context)
    if data.startswith("wd_ok:"):
        return await wd_ok(update, context)
    if data.startswith("wd_no:"):
        return await wd_no(update, context)
    if data == "back_menu":
        return await back_menu(update, context)

# --------- MAIN ----------
def main():
    load_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    # text input for email/upi during withdraw
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, wd_email))
    app.add_handler(CallbackQueryHandler(button_router))

    print("✅ Bot started... (Render)")
    app.run_polling()

if __name__ == "__main__":
    main()
