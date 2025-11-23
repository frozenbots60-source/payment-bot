import asyncio
import logging
import time
import requests
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, Button, functions, types
from pymongo import MongoClient

# ================== CONFIG ==================

API_ID = 29568441
API_HASH = "b32ec0fb66d22da6f77d355fbace4f2a"
BOT_TOKEN = "8302453295:AAEAmmqF4YrhGC1zDBI8CXH-52sil6kePKU"

SUPPORT_CHAT_LINK = "https://t.me/kustbotschat"
UPDATES_CHANNEL_LINK = "https://t.me/kustbots"
UPI_DM_LINK = "https://t.me/KustXoffical"

# Messages to forward
FORWARD_1 = ("kustvault", 3)
FORWARD_2 = ("kustvault", 2)
FORWARD_3 = ("kustvault", 4)

# Start image
START_IMAGE_URL = "https://filehosting.kustbotsweb.workers.dev/-p_.jpg"

# MongoDB
MONGO_URL = "mongodb+srv://kustbotsweb_db_user:z7YqNFmFOvVHKl4B@kust-payments.hiin3lu.mongodb.net/?appName=kust-payments"
mongo = MongoClient(MONGO_URL)
db = mongo["kustfarm"]
users_col = db["users"]
demos_col = db["demos"]

# Bot owner
BOT_OWNER_ID = 7618467489

# OxaPay API
OXAPAY_API_KEY = "SNJEE3-MOEI0B-ZR0FW4-UWSLXH"
OXAPAY_API_BASE = "https://api.oxapay.com"

ACTIVATION_API_URL = "https://chat-auth-75bd02aa400a.herokuapp.com/auth"

PLANS = {
    "1d": {"label": "1 Day",  "amount": 0.1,  "hours": 24},
    "2d": {"label": "2 Days", "amount": 4.3,  "hours": 48},
    "4d": {"label": "4 Days", "amount": 7.8,  "hours": 96},
    "7d": {"label": "7 Days", "amount": 13.3, "hours": 168},
}

PAYMENT_TIMEOUT = 15 * 60
POLL_INTERVAL = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("stake_farmer_payment_bot")

bot = TelegramClient("stake_farmer_payment_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

user_sessions = {}
user_tasks = {}

# ================== OXAPAY HELPERS ==================

def create_invoice(amount: float, currency: str = "USDT", lifetime: int = 60):
    url = f"{OXAPAY_API_BASE}/v1/payment/invoice"
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}
    body = {"amount": amount, "currency": currency, "lifetime": lifetime}
    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.json()

def query_invoice(track_id: str):
    url = f"{OXAPAY_API_BASE}/merchants/inquiry"
    headers = {"Content-Type": "application/json"}
    body = {"merchant": OXAPAY_API_KEY, "trackId": track_id}
    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.json()

def activate_subscription(username_with_at: str, hours: int):
    try:
        # API expects duration in hours. Send hours directly.
        params = {
            "user": username_with_at,
            "admin": "admin1234",
            "duration": hours
        }
        url = ACTIVATION_API_URL
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        logger.info(f"Activated subscription for {username_with_at} for {hours} hours")
    except Exception as e:
        logger.error(f"Failed activation API: {e}")

async def wait_for_payment(user_id: int, track_id: str, plan_key: str):
    session = user_sessions.get(user_id)
    if not session:
        return False

    plan = PLANS.get(plan_key)
    if not plan:
        return False

    label = plan["label"]
    hours = plan["hours"]

    start = time.time()
    while time.time() - start < PAYMENT_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            data = await asyncio.to_thread(query_invoice, track_id)
            status = data.get("status", "").lower()

            if status == "paid":
                username_clean = session.get("username", "UNKNOWN")

                activate_subscription(f"@{username_clean}", hours)

                await bot.send_message(
                    user_id,
                    f"✅ Payment confirmed!\n\n"
                    f"Your <b>{label}</b> subscription is activated.\n"
                    f"Stake Username: <code>@{username_clean}</code>\n"
                    f"Duration: <b>{hours} hours</b>.",
                    parse_mode="html"
                )

                # FORWARD + PIN (now includes the third message)
                for chat, msg_id in [FORWARD_1, FORWARD_2, FORWARD_3]:
                    try:
                        fwd = await bot.forward_messages(user_id, msg_id, from_peer=chat)
                        if isinstance(fwd, list):
                            fwd = fwd[0]
                        try:
                            await bot.pin_message(user_id, fwd.id, notify=True)
                        except:
                            pass
                    except Exception as e:
                        logger.error(f"Forward error: {e}")

                return True

            if status in ("expired", "cancelled"):
                await bot.send_message(user_id, f"❌ Invoice for {label} expired or cancelled.")
                return False

        except Exception as e:
            logger.error(f"Invoice query error: {e}")

    await bot.send_message(user_id, "⏳ Payment not confirmed. Create a new invoice.")
    return False

# ================== HANDLERS ==================

@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    user_id = event.sender_id

    # React to /start instantly
    try:
        await bot(functions.messages.SendReactionRequest(
            peer=event.chat_id,
            msg_id=event.message.id,
            reaction=[types.ReactionEmoji(emoticon='👍')],
            add_to_recent=False
        ))
    except:
        pass

    # Check first-time user
    try:
        existing = users_col.find_one({"user_id": user_id})
    except:
        existing = None

    first_time = existing is None

    # Save user
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "first_seen": datetime.now(timezone.utc)}},
        upsert=True
    )

    # Caption text to appear with the image
    caption_text = (
        "<b>🚀 Kust Bots — Stake Chat Farmer & AI Chat Engine</b>\n\n"
        "⚡ Automated Chat Farming • AI-Driven Replies • Stealth Anti-Detection Engine\n\n"
        "Tap a button below to continue."
    )

    # Buttons (same set, displayed under the image caption)
    if first_time:
        buttons = [
            [Button.inline("🎁 Get your free demo now", b"get_demo")],
            [
                Button.url("🛠 Support", SUPPORT_CHAT_LINK),
                Button.url("📢 Updates", UPDATES_CHANNEL_LINK),
            ],
        ]
    else:
        buttons = [
            [Button.inline("💰 Buy Subscription", b"buy_sub")],
            [
                Button.url("🛠 Support", SUPPORT_CHAT_LINK),
                Button.url("📢 Updates", UPDATES_CHANNEL_LINK),
            ],
        ]

    user_sessions[user_id] = {"expecting_username": False}

    # Send the image with the caption, falling back to a text response if sending the file fails
    try:
        await bot.send_file(user_id, START_IMAGE_URL, caption=caption_text, parse_mode="html", buttons=buttons)
    except Exception as e:
        logger.error(f"send_file failed: {e}")
        text = (
            "<b>🚀 Kust Bots — Stake Chat Farmer & AI Chat Engine</b>\n\n"
            "⚡ Automated Chat Farming • AI-Driven Replies • Stealth Anti-Detection Engine\n\n"
            "Tap a button below to continue."
        )
        await event.respond(text, parse_mode="html", buttons=buttons)

@bot.on(events.NewMessage(pattern=r"^/(help|support)$"))
async def help_handler(event):
    await event.respond(
        "For issues, join support chat:",
        buttons=[[Button.url("🛠 Support Chat", SUPPORT_CHAT_LINK)]]
    )

@bot.on(events.CallbackQuery(data=b"buy_sub"))
async def buy_sub_handler(event):
    await event.answer()
    user_id = event.sender_id

    session = user_sessions.setdefault(user_id, {})
    session["expecting_username"] = True
    session.pop("demo_request", None)

    text = (
        "<b>Buy Subscription — Step 1: Provide your Stake username</b>\n\n"
        "Send only the username. Examples:\n"
        "• <code>alice123</code>\n"
        "• <code>@alice123</code>\n\n"
        "Do NOT send profile links or screenshots. After you send the username you'll be asked to confirm it."
    )
    try:
        await event.edit(text, parse_mode="html")
    except:
        await event.respond(text, parse_mode="html")

@bot.on(events.CallbackQuery(data=b"get_demo"))
async def get_demo_handler(event):
    await event.answer()
    user_id = event.sender_id

    session = user_sessions.setdefault(user_id, {})
    session["expecting_username"] = True
    session["demo_request"] = True

    text = (
        "🎁 <b>Free Demo (3 hours) — Step 1: Provide your Stake username</b>\n\n"
        "Send only the username. Examples:\n"
        "• <code>alice123</code>\n"
        "• <code>@alice123</code>\n\n"
        "One demo per Telegram account + Stake username. After you send the username you'll be asked to confirm it."
    )
    try:
        await event.edit(text, parse_mode="html")
    except:
        await event.respond(text, parse_mode="html")

# When a username-like message is received, store it as pending and ask for confirmation
@bot.on(events.NewMessage(pattern=r"^[A-Za-z0-9_@]{3,51}$"))
async def username_handler(event):
    user_id = event.sender_id
    session = user_sessions.setdefault(user_id, {})

    if not session.get("expecting_username"):
        return  # ignore unless we asked for it

    raw_username = event.raw_text.strip()
    username_clean = raw_username.lstrip('@')

    # Save as pending until user confirms
    session["pending_username"] = username_clean
    session["expecting_username"] = False

    text = (
        "You entered the Stake username:\n\n"
        f"<b>@{username_clean}</b>\n\n"
        "Is this correct?"
    )
    buttons = [
        [Button.inline("✅ Yes, this is my username", b"confirm_username_yes")],
        [Button.inline("✏️ No — Edit username", b"confirm_username_no")],
    ]

    await event.respond(text, parse_mode="html", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"confirm_username_no"))
async def confirm_no_handler(event):
    await event.answer()
    user_id = event.sender_id
    session = user_sessions.setdefault(user_id, {})

    # Allow user to send username again
    session["expecting_username"] = True
    session.pop("pending_username", None)

    text = (
        "Okay — please send your Stake username again.\n\n"
        "Examples:\n"
        "• <code>alice123</code>\n"
        "• <code>@alice123</code>\n\n"
        "Send only the username (no links)."
    )
    try:
        await event.edit(text, parse_mode="html")
    except:
        await event.respond(text, parse_mode="html")

@bot.on(events.CallbackQuery(data=b"confirm_username_yes"))
async def confirm_yes_handler(event):
    await event.answer()
    user_id = event.sender_id
    session = user_sessions.get(user_id)

    if not session:
        return await event.respond("Session expired. Restart with /start.")

    pending = session.get("pending_username")
    if not pending:
        return await event.respond("No username pending. Please restart with /start and try again.")

    username_clean = pending
    session.pop("pending_username", None)
    session["username"] = username_clean
    session["expecting_username"] = False

    # If this was a demo request, proceed with demo activation
    if session.get("demo_request"):
        already = demos_col.find_one({"$or": [{"user_id": user_id}, {"username": username_clean}]})
        if already:
            session.pop("demo_request", None)
            return await event.respond("❌ Demo already used by this username or Telegram account.")

        expires_at = datetime.now(timezone.utc) + timedelta(hours=3)
        demos_col.insert_one({"user_id": user_id, "username": username_clean, "expires_at": expires_at})
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"demo_used": True, "demo_expires": expires_at, "demo_username": username_clean}},
            upsert=True
        )

        activate_subscription(f"@{username_clean}", 3)

        # Prepare response message
        text = (
            f"✅ Demo activated for <code>@{username_clean}</code>\n"
            f"Duration: 3 hours."
        )
        try:
            await event.edit(text, parse_mode="html")
        except:
            await event.respond(text, parse_mode="html")

        # FORWARD THREE messages and try to pin
        for chat, msg_id in [FORWARD_1, FORWARD_2, FORWARD_3]:
            try:
                fwd = await bot.forward_messages(user_id, msg_id, from_peer=chat)
                if isinstance(fwd, list):
                    fwd = fwd[0]
                try:
                    await bot.pin_message(user_id, fwd.id, notify=True)
                except:
                    pass
            except Exception as e:
                logger.error(f"Demo forward error: {e}")

        session.pop("demo_request", None)
        return

    # Otherwise proceed to purchase flow: show payment method selection
    text = (
        f"Stake username saved: <code>@{username_clean}</code>\n\n"
        "Choose payment method:"
    )
    buttons = [
        [Button.inline("💳 Buy with Crypto", b"buy_crypto")],
        [Button.inline("💵 Buy with UPI", b"buy_upi")],
    ]

    try:
        await event.edit(text, parse_mode="html", buttons=buttons)
    except:
        await event.respond(text, parse_mode="html", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"buy_upi"))
async def buy_upi_handler(event):
    await event.answer()
    text = (
        "💵 <b>Buy with UPI</b>\n\n"
        "DM admin and mention your Stake username:\n"
        f"👉 <a href=\"{UPI_DM_LINK}\">@KustXoffical</a>"
    )
    buttons = [[Button.url("DM for UPI Payment", UPI_DM_LINK)]]

    try:
        await event.edit(text, parse_mode="html", buttons=buttons)
    except:
        await event.respond(text, parse_mode="html", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"buy_crypto"))
async def buy_crypto_handler(event):
    await event.answer()
    user_id = event.sender_id
    session = user_sessions.get(user_id)

    if not session or "username" not in session:
        return await event.respond("Restart with /start and send your username.")

    text = (
        "💳 <b>Buy with Crypto (OxaPay)</b>\n\n"
        "Plans:\n"
        "• 1 Day  — 2 USDT\n"
        "• 2 Days — 4 USDT\n"
        "• 4 Days — 7.5 USDT\n"
        "• 7 Days — 13 USDT\n\n"
        "Select your plan:"
    )

    buttons = [
        [
            Button.inline("1 Day — 2.3 USDT", b"plan_1d"),
            Button.inline("2 Days — 4.3 USDT", b"plan_2d"),
        ],
        [
            Button.inline("4 Days — 7.8 USDT", b"plan_4d"),
            Button.inline("7 Days — 13.3 USDT", b"plan_7d"),
        ],
    ]

    try:
        await event.edit(text, parse_mode="html", buttons=buttons)
    except:
        await event.respond(text, parse_mode="html", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"plan_"))
async def plan_handler(event):
    await event.answer()
    user_id = event.sender_id
    session = user_sessions.get(user_id)

    if not session or "username" not in session:
        return await event.respond("Restart with /start and send your username first.")

    plan_key = event.data.decode().split("_", 1)[1]
    plan = PLANS.get(plan_key)
    if not plan:
        return await event.respond("Invalid plan. Try again.")

    amount = plan["amount"]
    label = plan["label"]

    if user_id in user_tasks:
        old = user_tasks[user_id]
        if not old.done():
            old.cancel()

    try:
        resp = await asyncio.to_thread(create_invoice, amount)
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        return await event.respond("Failed to create invoice.")

    data = resp.get("data", {})
    track_id = data.get("track_id") or data.get("trackId")
    pay_url = data.get("payment_url") or data.get("paymentUrl")

    if not track_id or not pay_url:
        return await event.respond("Payment gateway error.")

    session["track_id"] = track_id
    session["plan_key"] = plan_key

    text = (
        f"✅ Plan: <b>{label}</b>\n"
        f"Amount: <b>{amount} USDT</b>\n\n"
        "Click <b>Pay</b> to open OxaPay.\n"
        "Payment window: 15 minutes."
    )
    buttons = [
        [Button.url("🔗 Pay", pay_url)],
        [
            Button.url("🛠 Support", SUPPORT_CHAT_LINK),
            Button.url("📢 Updates", UPDATES_CHANNEL_LINK),
        ],
    ]
    try:
        await event.edit(text, parse_mode="html", buttons=buttons)
    except:
        await event.respond(text, parse_mode="html", buttons=buttons)

    task = asyncio.create_task(wait_for_payment(user_id, track_id, plan_key))
    user_tasks[user_id] = task

# ================== BROADCAST ==================

@bot.on(events.NewMessage(pattern=r"^/broadcast$"))
async def broadcast_handler(event):
    if event.sender_id != BOT_OWNER_ID:
        return await event.reply("❌ Unauthorized.")

    if not event.is_reply:
        return await event.reply("Reply to a message with /broadcast.")

    orig = await event.get_reply_message()
    if not orig:
        return await event.reply("Message not found.")

    total = 0
    cursor = users_col.find({}, {"user_id": 1})

    for u in cursor:
        uid = u.get("user_id")
        if not uid:
            continue

        try:
            fwd = await bot.forward_messages(uid, orig.id, from_peer=event.chat_id)
            if isinstance(fwd, list):
                fwd = fwd[0]

            try:
                await bot.pin_message(uid, fwd.id, notify=True)
            except:
                pass

            total += 1
        except Exception as e:
            logger.error(f"Broadcast fail to {uid}: {e}")

    await event.reply(f"✅ Broadcast sent to {total} users.")

# ================== MAIN ==================

def main():
    logger.info("Stake Farmer Payment Bot is running...")
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
