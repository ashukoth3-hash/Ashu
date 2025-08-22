# -*- coding: utf-8 -*-
# Refer–Earn Telegram Bot (python-telegram-bot v21)
# Author: you ✨

import os, json, asyncio, time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.error import Forbidden

# ===================== CONFIG =====================

# Token: ENV se le (Render par "BOT_TOKEN" env var lagana)
BOT_TOKEN = os.getenv("7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU", "7573978624:AAG9Ki0ZVglaAHH_c-fUOF7KoTOOuYIDKrU").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# Admins (comma se add kar sakte ho)
ADMINS = {1898098929}

# Join-force channels (usernames WITHOUT @)
REQUIRED_CHANNELS = [
    "loot4udeal",
    "free_redeem_codes_fire_crypto",
    "crypto_free_redeem_codes_fire",
]

# Proof channel (username WITHOUT @)
PROOF_CHANNEL = "vipredeem"

# Coins config
SIGNUP_BONUS = 50
DAILY_BONUS  = 10
REFER_COIN   = 100

# Withdraw slabs: (required_coins, label/text)
WITHDRAW_OPTIONS: List[Tuple[int, str]] = [
    (2000,  "₹10"),
    (4000,  "₹20"),
    (8000,  "₹45"),  # 40 + 5 extra
]

# ===================== DB =====================

DB_FILE = "db.json"
DB_LOCK = asyncio.Lock()
db: Dict[str, Any] = {"users": {}, "withdraws": []}  # simple JSON store


def _now_ts() -> int:
    return int(time.time())


def _human_td(seconds: int) -> str:
    # 90061 -> "1d 1h 1m"
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return " ".join(parts) or "0m"


def load_db() -> None:
    global db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {"users": {}, "withdraws": []}


def save_db() -> None:
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_FILE)


def get_user(uid: int) -> Dict[str, Any]:
    suid = str(uid)
    if suid not in db["users"]:
        db["users"][suid] = {
            "coins": 0,
            "verified": False,
            "ref_by": None,
            "ref_credited": False,
            "refs": [],
            "last_bonus_at": 0,   # unix ts
            "email": None,
        }
    return db["users"][suid]


# ===================== UI HELPERS =====================

def name_of(u: Update) -> str:
    user = u.effective_user
    first = (user.first_name or "").strip()
    return first or "User"


def join_force_keyboard() -> InlineKeyboardMarkup:
    rows = []
    # Join buttons
    join_buttons = []
    for idx, uname in enumerate(REQUIRED_CHANNELS, start=1):
        url = f"https://t.me/{uname}"
        join_buttons.append(InlineKeyboardButton(f"Join {idx}", url=url))
        if len(join_buttons) == 2:
            rows.append(join_buttons)
            join_buttons = []
    if join_buttons:
        rows.append(join_buttons)
    # Claim button
    rows.append([InlineKeyboardButton("✅ Claim", callback_data="claim_join")])
    return InlineKeyboardMarkup(rows)


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Balance",  callback_data="balance"),
         InlineKeyboardButton("👥 Refer",     callback_data="refer")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("✉️ Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🧾 Proof",     callback_data="proof")]
    ])


def withdraw_keyboard() -> InlineKeyboardMarkup:
    rows = []
    btns = []
    for need, label in WITHDRAW_OPTIONS:
        btns.append(InlineKeyboardButton(f"{need} coins – {label}",
                                         callback_data=f"wd_{need}"))
        if len(btns) == 1:
            rows.append(btns)
            btns = []
    if btns:
        rows.append(btns)
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
    return InlineKeyboardMarkup(rows)


async def is_joined_everywhere(context: ContextTypes.DEFAULT_TYPE, uid: int) -> bool:
    ok = True
    for uname in REQUIRED_CHANNELS:
        try:
            cm: ChatMember = await context.bot.get_chat_member(f"@{uname}", uid)
            status = cm.status
            if status not in ("member", "administrator", "creator"):
                ok = False
                break
        except Forbidden:
            # bot not admin in channel or channel privacy — treat as not joined
            ok = False
            break
        except Exception:
            ok = False
            break
    return ok


async def ensure_verified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    async with DB_LOCK:
        u = get_user(uid)
        verified = u["verified"]
    if verified:
        return True

    # Not verified -> show join panel
    await update.effective_message.reply_text(
        f"😍 Hey !! <b>{name_of(update)}</b> Welcome To Bot\n"
        "🟢 Must Join All Channels To Use Bot\n"
        "⬛ After Joining click <b>Claim</b>",
        reply_markup=join_force_keyboard(),
        parse_mode="HTML",
    )
    return False


# ===================== USER HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    args = context.args or []

    async with DB_LOCK:
        u = get_user(uid)
        # attach referral on first start
        if args:
            ref = args[0]
            if ref.isdigit():
                rid = int(ref)
                if rid != uid and u["ref_by"] is None:
                    u["ref_by"] = rid
        save_db()

    # Start panel (join-force first)
    await update.message.reply_text(
        f"😍 Hey !! <b>{name_of(update)}</b> Welcome To Bot\n"
        "🟢 Must Join All Channels To Use Bot\n"
        "⬛ After Joining click <b>Claim</b>",
        reply_markup=join_force_keyboard(),
        parse_mode="HTML",
    )

    # Also show main menu for those already verified
    async with DB_LOCK:
        already = get_user(uid)["verified"]
    if already:
        await update.message.reply_text("✅ Bot live! Try /ping",
                                        reply_markup=main_menu_kb())


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong")


async def on_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_verified(update, context):
        return
    await update.effective_message.reply_text("✅ Bot live! Try /ping",
                                              reply_markup=main_menu_kb())


async def on_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    joined = await is_joined_everywhere(context, uid)
    async with DB_LOCK:
        u = get_user(uid)
        if joined:
            if not u["verified"]:
                u["verified"] = True
                u["coins"] += SIGNUP_BONUS

                # credit referrer once
                if u["ref_by"] and not u["ref_credited"]:
                    ref_id = u["ref_by"]
                    ref_u = get_user(ref_id)
                    ref_u["coins"] += REFER_COIN
                    ref_u["refs"].append(uid)
                    u["ref_credited"] = True
                    save_db()
                    try:
                        await context.bot.send_message(
                            ref_id,
                            f"✅ <b>1 Refer Successful!</b>\n"
                            f"+{REFER_COIN} coins added.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            save_db()

    if not joined:
        await q.edit_message_text(
            "⚠️ Abhi tak aapne sabhi channels join nahi kiye.\n"
            "Please join and then tap <b>Claim</b>.",
            reply_markup=join_force_keyboard(), parse_mode="HTML"
        )
        return

    # Success -> show menu
    await q.edit_message_text(
        f"🎉 Verification complete! {SIGNUP_BONUS} coins added.\n"
        "Ab niche se options use karein.",
        reply_markup=main_menu_kb()
    )


async def on_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await ensure_verified(update, context):
        return

    uid = q.from_user.id
    async with DB_LOCK:
        coins = get_user(uid)["coins"]

    msg = (
        f"Hello 👋 <b>{q.from_user.first_name}</b>\n\n"
        f"APKA ABHI BALANCE H 🤑 <b>{coins} coins</b>\n"
        f"MINIMUM WITHDRAWAL <b>{WITHDRAW_OPTIONS[0][0]} coins</b> ka h."
    )
    await q.edit_message_text(msg, reply_markup=main_menu_kb(), parse_mode="HTML")


async def on_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await ensure_verified(update, context):
        return

    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={q.from_user.id}"

    msg = (
        f"Hello 👋 <b>{q.from_user.first_name}</b>\n"
        f"Apka Referral Link 👇\n{link}\n\n"
        f"Per Refer = <b>{REFER_COIN} coins</b> 🪙\n"
        "🔴 Not Fake Refer Allowed."
    )
    await q.edit_message_text(msg, reply_markup=main_menu_kb(), parse_mode="HTML")


async def on_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await ensure_verified(update, context):
        return

    uid = q.from_user.id
    now = _now_ts()
    async with DB_LOCK:
        u = get_user(uid)
        last = u["last_bonus_at"]
        if now - last >= 24 * 3600:
            u["coins"] += DAILY_BONUS
            u["last_bonus_at"] = now
            save_db()
            got = True
        else:
            got = False
            left = 24 * 3600 - (now - last)

    if got:
        text = (
            f"Hello 👋 <b>{q.from_user.first_name}</b>\n"
            f"Daily bonus har 24 hours me add hota hai.\n"
            f"Aaj ka bonus: +{DAILY_BONUS} coins ✅"
        )
    else:
        text = (
            f"Hello 👋 <b>{q.from_user.first_name}</b>\n"
            "Daily bonus har 24 hours me add hota hai.\n"
            f"Next bonus in: <b>{_human_td(left)}</b>"
        )

    await q.edit_message_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ---------- Withdraw flow ----------
ASK_EMAIL, = range(1)

async def on_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await ensure_verified(update, context):
        return

    uid = q.from_user.id
    async with DB_LOCK:
        coins = get_user(uid)["coins"]

    msg = (
        f"Hello 👋 <b>{q.from_user.first_name}</b>\n"
        f"Aapka balance: <b>{coins} coins</b>\n\n"
        "Withdrawal 1–2 hours me aapke <b>email</b> par aa jayega.\n"
        "Amount choose karein:"
    )
    await q.edit_message_text(msg, reply_markup=withdraw_keyboard(), parse_mode="HTML")


async def wd_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await ensure_verified(update, context):
        return

    uid = q.from_user.id
    data = q.data  # wd_<coins> or home

    if data == "home":
        await q.edit_message_text("Menu:", reply_markup=main_menu_kb())
        return

    need = int(data.split("_")[1])

    async with DB_LOCK:
        u = get_user(uid)
        coins = u["coins"]

    if coins < need:
        await q.edit_message_text(
            f"⚠️ Aapke paas itne coins nahi hain. Required: {need}.",
            reply_markup=withdraw_keyboard()
        )
        return

    # store choice
    context.user_data["wd_need"] = need
    await q.edit_message_text(
        "📝 Email bhejein jisme aap code lena chahte ho.\n\n"
        "Example: <code>name@example.com</code>",
        parse_mode="HTML"
    )
    return ASK_EMAIL


async def wd_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    email = (update.message.text or "").strip()

    # very light check
    if "@" not in email or "." not in email:
        await update.message.reply_text("❌ Email galat lag rha hai, dubara bhejein.")
        return ASK_EMAIL

    need = context.user_data.get("wd_need")

    # Deduct + create pending request
    async with DB_LOCK:
        u = get_user(uid)
        if u["coins"] < need:
            await update.message.reply_text("⚠️ Coins kam ho gaye, dubara try karo.")
            return ConversationHandler.END

        u["coins"] -= need
        wd_id = f"wd_{int(time.time())}_{uid}"
        db["withdraws"].append({
            "id": wd_id,
            "uid": uid,
            "amount": need,
            "label": next((lbl for c,lbl in WITHDRAW_OPTIONS if c == need), ""),
            "email": email,
            "ts": _now_ts(),
            "status": "pending",
        })
        save_db()

    await update.message.reply_text(
        "✅ Withdrawal request received!\n"
        "1–2 ghante me aapke email par code aa jayega.\n"
        "Admin approval pending…",
        reply_markup=main_menu_kb()
    )

    # Notify admins with approve/reject buttons
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"appr_{wd_id}"),
         InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{wd_id}")]
    ])
    text = (f"🟡 New WD Request\n"
            f"ID: {wd_id}\nUser: <code>{uid}</code>\n"
            f"Amount: {need} coins\nEmail: {email}")
    for admin in ADMINS:
        try:
            await context.bot.send_message(admin, text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    return ConversationHandler.END


# ---------- Proof ----------

async def on_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, Update) and update.callback_query:
        q = update.callback_query
        await q.answer()
        msgf = q.edit_message_text
    else:
        msgf = update.message.reply_text

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Open Proof Channel", url=f"https://t.me/{PROOF_CHANNEL}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="home")]
    ])
    await msgf("Proofs yahan milenge:", reply_markup=btn)


# ===================== ADMIN =====================

ADMIN_ADD, ADMIN_DEDUCT, ADMIN_BCAST = range(3)

def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Coins", callback_data="ad_add"),
         InlineKeyboardButton("➖ Deduct Coins", callback_data="ad_deduct")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="ad_cast")],
        [InlineKeyboardButton("🟡 Pending WDs", callback_data="ad_wds")]
    ])


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in ADMINS:
            return
        return await func(update, context)
    return wrapper


@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👮 Admin Panel", reply_markup=admin_kb())


@admin_only
async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data
    if data == "ad_add":
        await q.edit_message_text("Send: <code>user_id coins</code>", parse_mode="HTML")
        return ADMIN_ADD
    if data == "ad_deduct":
        await q.edit_message_text("Send: <code>user_id coins</code>", parse_mode="HTML")
        return ADMIN_DEDUCT
    if data == "ad_cast":
        await q.edit_message_text("Send broadcast message (text/photo/caption).")
        return ADMIN_BCAST
    if data == "ad_wds":
        async with DB_LOCK:
            pend = [w for w in db["withdraws"] if w["status"] == "pending"]
        if not pend:
            await q.edit_message_text("No pending withdrawals.", reply_markup=admin_kb())
            return ConversationHandler.END
        text = "Pending WDs:\n" + "\n".join(
            f"- {w['id']} • {w['amount']}c • uid {w['uid']} • {w['email']}" for w in pend[:10]
        )
        await q.edit_message_text(text, reply_markup=admin_kb())
        return ConversationHandler.END

    # Approve / Reject from notifications
    if data.startswith("appr_") or data.startswith("rej_"):
        wid = data.split("_", 1)[1]
        status = "approved" if data.startswith("appr_") else "rejected"

        async with DB_LOCK:
            w = next((x for x in db["withdraws"] if x["id"] == wid), None)
            if not w or w["status"] != "pending":
                await q.edit_message_text("Not found / already processed.")
                return ConversationHandler.END
            w["status"] = status
            save_db()

        try:
            await context.bot.send_message(
                w["uid"],
                f"🔔 Withdrawal {status.upper()}.\n"
                f"Amount: {w['amount']} coins • Email: {w['email']}"
            )
        except Exception:
            pass
        await q.edit_message_text(f"OK: {wid} -> {status}")
        return ConversationHandler.END

    return ConversationHandler.END


@admin_only
async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid_s, coins_s = update.message.text.strip().split()
        uid, coins = int(uid_s), int(coins_s)
    except Exception:
        await update.message.reply_text("Format galat. Example: <code>12345 100</code>", parse_mode="HTML")
        return ADMIN_ADD

    async with DB_LOCK:
        u = get_user(uid)
        u["coins"] += coins
        save_db()

    await update.message.reply_text(f"Done: {uid} +{coins} coins.", reply_markup=admin_kb())
    try:
        await context.bot.send_message(uid, f"🔔 Admin ne +{coins} coins add kiye.")
    except Exception:
        pass
    return ConversationHandler.END


@admin_only
async def admin_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid_s, coins_s = update.message.text.strip().split()
        uid, coins = int(uid_s), int(coins_s)
    except Exception:
        await update.message.reply_text("Format galat. Example: <code>12345 50</code>", parse_mode="HTML")
        return ADMIN_DEDUCT

    async with DB_LOCK:
        u = get_user(uid)
        u["coins"] = max(0, u["coins"] - coins)
        save_db()

    await update.message.reply_text(f"Done: {uid} -{coins} coins.", reply_markup=admin_kb())
    try:
        await context.bot.send_message(uid, f"🔔 Admin ne -{coins} coins deduct kiye.")
    except Exception:
        pass
    return ConversationHandler.END


@admin_only
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # forward style broadcast (text/caption only)
    # NOTE: heavy loops should be rate-limited
    async with DB_LOCK:
        uids = list(map(int, db["users"].keys()))

    cnt = 0
    for uid in uids:
        try:
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
                cap = update.message.caption or ""
                await context.bot.send_photo(uid, file_id, caption=cap)
            else:
                await context.bot.send_message(uid, update.message.text_html or update.message.text)
            cnt += 1
            await asyncio.sleep(0.05)
        except Exception:
            await asyncio.sleep(0.01)

    await update.message.reply_text(f"Broadcast sent to {cnt} users.", reply_markup=admin_kb())
    return ConversationHandler.END


# ===================== ROUTER =====================

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data

    if data == "claim_join":
        return await on_claim(update, context)
    if data == "home":
        return await on_home(update, context)
    if data == "balance":
        return await on_balance(update, context)
    if data == "refer":
        return await on_refer(update, context)
    if data == "daily_bonus":
        return await on_daily(update, context)
    if data == "withdraw":
        return await on_withdraw(update, context)
    if data.startswith("wd_"):
        return await wd_choose(update, context)
    if data == "proof":
        return await on_proof(update, context)
    if data.startswith(("appr_", "rej_", "ad_")):
        return await admin_cb(update, context)


def build_app() -> Application:
    load_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping",  ping))
    app.add_handler(CommandHandler("admin", admin_panel))

    # Buttons
    app.add_handler(CallbackQueryHandler(on_button))

    # Withdraw conversation (asks email)
    wd_conv = ConversationHandler(
        entry_points=[],
        states={ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, wd_email)]},
        fallbacks=[CommandHandler("start", start)],
        per_chat=True, per_user=True, per_message=False,
        name="wd_conv",
    )
    app.add_handler(wd_conv)

    # Admin conversations
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_cb, pattern="^ad_(add|deduct|cast|wds)$")],
        states={
            ADMIN_ADD:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add)],
            ADMIN_DEDUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_deduct)],
            ADMIN_BCAST:  [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, admin_broadcast)],
        },
        fallbacks=[CommandHandler("admin", admin_panel)],
        per_chat=True, per_user=True, per_message=False,
        name="admin_conv",
    )
    app.add_handler(admin_conv)

    return app


def main():
    app = build_app()
    print("✅ Bot started…")
    app.run_polling()


if __name__ == "__main__":
    main()
