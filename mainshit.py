import asyncio
import logging
import time
import requests
from telethon import TelegramClient, events, Button

# Telegram credentials — replace with yours
API_ID = 29568441            # replace with your API ID
API_HASH = "b32ec0fb66d22da6f77d355fbace4f2a"  # replace with your API hash
BOT_TOKEN = "8296029448:AAGBEIsUyFerlpkyM-G0XjnYfkJw4jd8gko"
SUPPORT_HANDLE = "kustbotssupport"
ANNOUNCE_CHANNEL = "KustBotsNetwork"
FORWARD_CHANNEL = "kustbotsnetwork"  # channel to forward from
FORWARD_MESSAGE_ID = 131             # message to forward

# OxaPay API key
OXAPAY_API_KEY = "I2VVQJ-B7LTRZ-YGRBFY-6ST5QD"
OXAPAY_API_BASE = "https://api.oxapay.com"

# Pricing plans
PLANS = {
    "1d": {"label": "1 Day", "amount": 0.1, "hours": 24},
    "7d": {"label": "7 Days", "amount": 20.0, "hours": 168}
}

PAYMENT_TIMEOUT = 15 * 60  # 15 minutes
POLL_INTERVAL = 10  # 10 seconds

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("oxapay_bot")

bot = TelegramClient("oxa1pay_bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Store user data: {user_id: {"username": stake_username, "track_id": str, "plan": str}}
user_sessions = {}


def create_invoice(amount: float, currency="USDT", lifetime=60):
    """
    Create an OxaPay invoice.
    """
    url = f"{OXAPAY_API_BASE}/v1/payment/invoice"
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}
    body = {"amount": amount, "currency": currency, "lifetime": lifetime}
    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def query_invoice(track_id: str):
    """
    Query invoice status using OxaPay API.
    """
    url = f"{OXAPAY_API_BASE}/merchants/inquiry"
    headers = {"Content-Type": "application/json"}
    body = {"merchant": OXAPAY_API_KEY, "trackId": track_id}
    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.json()


async def wait_for_payment(user_id: int, track_id: str, label: str, hours: int):
    """
    Poll OxaPay until payment is confirmed or timeout.
    After payment confirmation:
      - Call add user API
      - Forward premium message without forward tag
      - Notify user
    """
    start = time.time()
    while time.time() - start < PAYMENT_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            data = await asyncio.to_thread(query_invoice, track_id)
            status = data.get("status", "").lower()
            logger.info(f"OxaPay status for {track_id}: {status}")
            if status == "paid":
                username = user_sessions[user_id]["username"]
                # Call external API to register user
                url = f"https://tester1-lfpf.onrender.com/add?username={username}&plan={hours}hours"
                try:
                    requests.get(url, timeout=10)
                    logger.info(f"Registered {username} for {hours} hours via {url}")
                except Exception as e:
                    logger.error(f"Failed to call register API for {username}: {e}")

                # Notify user
                await bot.send_message(user_id, f"✅ Payment confirmed! Your {label} plan is now active for Stake username: {username}")

                # Forward premium activation message without forward tag
                try:
                    src_msg = await bot.get_messages(FORWARD_CHANNEL, ids=FORWARD_MESSAGE_ID)
                    if src_msg:
                        await bot.send_message(user_id, src_msg.message, file=src_msg.media)
                except Exception as e:
                    logger.error(f"Failed to send activation message to {user_id}: {e}")

                return True
            if status in ("expired", "cancelled"):
                await bot.send_message(user_id, f"❌ Your invoice for {label} has expired or was cancelled.")
                return False
        except Exception as e:
            logger.error(f"Error querying invoice {track_id}: {e}")
            continue
    await bot.send_message(user_id, f"⏳ Payment not confirmed in time. Please try again.")
    return False


@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    await event.respond(
        "Welcome! Please send me your Stake username.\n\n"
        "**Important:** Premium will be activated on this username. Don't misspell it!"
    )
    user_sessions[event.sender_id] = {}  # initialize empty session


@bot.on(events.NewMessage(pattern=r"^[A-Za-z0-9_]{3,50}$"))
async def username_handler(event):
    """
    Accept Stake username and prompt to buy premium.
    """
    if event.sender_id not in user_sessions:
        return  # only after /start
    username = event.raw_text.strip()
    user_sessions[event.sender_id]["username"] = username
    text = f"Username saved: `{username}`\n\nChoose your premium plan:"
    buttons = [[Button.inline("Buy Premium", b"buy")]]
    try:
        await event.edit(text, parse_mode="md", buttons=buttons)
    except Exception:
        await event.respond(text, parse_mode="md", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"support"))
async def support_handler(event):
    await event.answer()
    text = f"For help: @{SUPPORT_HANDLE}\nChannel: @{ANNOUNCE_CHANNEL}"
    try:
        await event.edit(text)
    except Exception:
        await event.respond(text)


@bot.on(events.CallbackQuery(data=b"buy"))
async def buy_handler(event):
    await event.answer()
    if "username" not in user_sessions.get(event.sender_id, {}):
        return await event.respond("Please restart with /start and provide your Stake username first.")
    buttons = [
        [Button.inline("1 Day — 5 USDT", b"plan_1d"),
         Button.inline("7 Days — 20 USDT", b"plan_7d")]
    ]
    text = "Choose your plan:"
    try:
        await event.edit(text, buttons=buttons)
    except Exception:
        await event.respond(text, buttons=buttons)


@bot.on(events.CallbackQuery(pattern=b"plan_"))
async def plan_handler(event):
    await event.answer()
    session = user_sessions.get(event.sender_id)
    if not session or "username" not in session:
        return await event.respond("Please restart with /start and provide your Stake username first.")

    plan_key = event.data.decode().split("_")[1]
    plan = PLANS.get(plan_key)
    if not plan:
        return await event.respond("Invalid plan selected.")

    amount = plan["amount"]
    label = plan["label"]
    hours = plan["hours"]
    logger.info(f"Plan {label} selected by user_id={event.sender_id}")

    try:
        logger.info(f"Creating invoice: {{'amount': {amount}, 'currency': 'USDT', 'lifetime': 60}}")
        resp = await asyncio.to_thread(create_invoice, amount)
        logger.info(f"Invoice API response: {resp}")
    except Exception as e:
        logger.error(f"Invoice creation error: {e}")
        return await event.respond("Failed to create invoice. Try again later.")

    data = resp.get("data", {})
    track_id = data.get("track_id")
    pay_url = data.get("payment_url")
    if not track_id or not pay_url:
        logger.error(f"Invalid response from OxaPay API for user {event.sender_id}: {resp}")
        return await event.respond("Invalid response from OxaPay API.")

    session["track_id"] = track_id
    session["plan"] = label

    text = (
        f"Plan: *{label}*\nAmount: *{amount} USDT*\n\nClick below to pay (choose your crypto):"
    )
    buttons = [
        [Button.url("Pay", pay_url),
         Button.url("Channel", f"https://t.me/{ANNOUNCE_CHANNEL}")]
    ]
    try:
        await event.edit(text, parse_mode="md", buttons=buttons)
    except Exception:
        await event.respond(text, parse_mode="md", buttons=buttons)

    # Start waiting for payment confirmation
    asyncio.create_task(wait_for_payment(event.sender_id, track_id, label, hours))


def main():
    logger.info("Bot is running...")
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()
