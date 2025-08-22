# main.py
import os, json, asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import Forbidden

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU") or "7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU"  # <-- Render/GitHub env var (DO NOT hardcode)

# Join-force channel usernames (WITHOUT @)
REQUIRED_CHANNELS: List[str] = [
    "free_redeem_codes_fire_crypto",
    "loot4udeal",
]

# Proof/withdrawal proof channel (username OR t.me link)
PROOF_CHANNEL = "Withdrawal_Proofsj"   # button will open this

# Admin IDs (comma separated if more)
ADMINS = [1898098929]

# Coins
SIGNUP_BONUS = 50
DAILY_BONUS  = 10
REFER_COIN   = 100
MIN_WITHDRAW = 2000

# ---- Withdraw options (slabs -> label)
WITHDRAW_OPTIONS = [
    (2000, "₹10"),
    (4000, "₹20"),
    (6000, "₹30"),
]

DB_FILE  = "db.json"
DB_LOCK  = asyncio.Lock()
db: Dict[str, Any] = {"users": {}}

# ---------- DB HELPERS ----------
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
            "pending_withdraw": None  # {"amount": coins, "label": "₹10"}
        }
    return db["users"][uid]

# ---------- UI ----------
def join_force_kb() -> InlineKeyboardMarkup:
    rows = []
    for ch in REQUIRED_CHANNELS:
        rows.append([InlineKeyboardButton("Join", url=f"https://t.me/{ch}")])
    rows.append([InlineKeyboardButton("✅ Claim", callback_data="claim_join")])
    return InlineKeyboardMarkup(rows)

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Refer",   callback_data="refer")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("📩 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🧾 Proof", callback_data="proof")]
    ])

WELCOME_TEXT = (
    "😍 Hey !! {name} Welcome To Bot\n"
    "🟢 Must Join All Channels To Use Bot\n"
    "⬛ After Joining click Claim"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    name  = update.effective_user.first_name or "User"
    args  = context.args or []

    async with DB_LOCK:
        u = get_user(uid)

        # referral attach (only once)
        if args:
            ref = args[0]
            if ref.isdigit() and int(ref) != uid and u.get("ref_by") is None:
                u["ref_by"] = int(ref)
                save_db()

        # If not verified yet → show join panel
        verified = get_user(uid).get("verified", False)

    if not verified:
        await update.message.reply_text(WELCOME_TEXT.format(name=name),
                                        reply_markup=join_force_kb())
        return

    # If verified, give signup bonus once
    async with DB_LOCK:
        u = get_user(uid)
        if not u["joined_bonus_done"]:
            u["coins"] += SIGNUP_BONUS
            u["joined_bonus_done"] = True
            save_db()

    await update.message.reply_text("✅ Bot live! Try /ping",
                                    reply_markup=main_menu_kb())

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong")

# ---------- VERIFY JOIN ----------
async def claim_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    name  = query.from_user.first_name or "User"

    # Check membership for each required channel
    try:
        for ch in REQUIRED_CHANNELS:
            member = await context.bot.get_chat_member(f"@{ch}", uid)
            if member.status in ("left", "kicked"):
                await query.edit_message_text(
                    "❌ Abhi sab channels join nahi hue. Pehle join karo, phir Claim dabao.",
                    reply_markup=join_force_kb()
                )
                return
    except Forbidden:
        # If bot not admin / cannot access: still show keyboard
        await query.edit_message_text(
            "⚠️ Bot ko channels dekhne ka access nahi mila. Pehle ensure karo bot ko add kiya gaya hai.",
            reply_markup=join_force_kb()
        )
        return

    # Mark verified
    async with DB_LOCK:
        u = get_user(uid)
        if not u["verified"]:
            u["verified"] = True

            # Signup bonus if not already
            if not u["joined_bonus_done"]:
                u["coins"] += SIGNUP_BONUS
                u["joined_bonus_done"] = True

            # Referral credit (and notify referrer)
            if u.get("ref_by"):
                ref_id = u["ref_by"]
                ref_u  = get_user(ref_id)
                ref_u["coins"] += REFER_COIN
                ref_u["refs"]  += 1
                save_db()
                # Notify referrer
                try:
                    await context.bot.send_message(
                        ref_id,
                        f"✅ 1 Refer successful!\n"
                        f"🥳 Aapko +{REFER_COIN} coins mile!"
                    )
                except Exception:
                    pass
        save_db()

    await query.edit_message_text(
        "✅ Verification complete! Menu se choose karo.",
        reply_markup=main_menu_kb()
    )

# ---------- CALLBACKS ----------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    uid   = query.from_user.id
    name  = query.from_user.first_name or "User"

    if data == "claim_join":
        await claim_join(update, context)
        return

    async with DB_LOCK:
        u = get_user(uid)
        save_db()

    if data == "balance":
        txt = (
            f"Hello 👋 {name}\n\n"
            f"APKA ABHI BALANCE H 🤑 {u['coins']} COINS\n\n"
            f"MINIMUM WITHDRAWAL {MIN_WITHDRAW} COIN KA H"
        )
        await query.answer()
        await query.edit_message_text(txt, reply_markup=main_menu_kb())

    elif data == "refer":
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start={uid}"
        txt = (
            f"Hello 👋 {name}  Apka Referral Link 👇\n"
            f"{ref_link}\n\n"
            f"Per Refer = {REFER_COIN} coin 🪙\n\n"
            f"🔴 Not Fake Refer Not Allow"
        )
        await query.answer()
        await query.edit_message_text(txt, reply_markup=main_menu_kb())

    elif data == "withdraw":
        opts = "\n".join([f"- {c} coins → {lab}" for c, lab in WITHDRAW_OPTIONS])
        txt = (
            f"Hello 👋 {name}  Aapka BALANCE: {u['coins']} coins\n\n"
            f"Minimum: {MIN_WITHDRAW}\n"
            f"Options:\n{opts}\n\n"
            f"Withdrawal 1-2 Hours Me aapke Email par aa Jayega"
        )
        await query.answer()
        await query.edit_message_text(txt, reply_markup=main_menu_kb())

    elif data == "daily_bonus":
        # 24 hours cool-down
        now  = datetime.utcnow()
        last = u.get("last_bonus_date")
        allowed = True
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if now - last_dt < timedelta(hours=24):
                    left = timedelta(hours=24) - (now - last_dt)
                    hrs = int(left.total_seconds() // 3600)
                    mins = int((left.total_seconds() % 3600) // 60)
                    txt = (
                        f"Hello 👋 {name}\n"
                        f"Daily bonus har 24 hours me add hota hai.\n"
                        f"Agle bonus ke liye: {hrs}h {mins}m baaki."
                    )
                    allowed = False
            except Exception:
                pass

        if allowed:
            u["coins"] += DAILY_BONUS
            u["last_bonus_date"] = now.isoformat()
            save_db()
            txt = (
                f"Hello 👋 {name} Daily bonus har 24 hours me add hoga\n"
                f"🎁 +{DAILY_BONUS} coins added!\n"
                f"New balance: {u['coins']} coins"
            )
        await query.answer()
        await query.edit_message_text(txt, reply_markup=main_menu_kb())

    elif data == "proof":
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔗 Open Proof Channel",
                                   url=f"https://t.me/{PROOF_CHANNEL}")]]
        )
        await query.answer()
        await query.edit_message_text("🧾 Proofs yahan milenge:", reply_markup=btn)

# ---------- ADMIN (simple) ----------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMINS:
        return
    async with DB_LOCK:
        total_users = len(db["users"])
        verified    = sum(1 for u in db["users"].values() if u.get("verified"))
        refs_sum    = sum(u.get("refs", 0) for u in db["users"].values())
    txt = (
        "🛠️ Admin Panel\n"
        f"Users: {total_users}\n"
        f"Verified: {verified}\n"
        f"Total Refs: {refs_sum}\n"
    )
    await update.message.reply_text(txt)

# ---------- ENTRY ----------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")

    load_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping",  ping))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(on_callback))

    print("✅ Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
