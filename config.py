import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DB_PATH = ROOT / "bot.db"
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# SHA-256 of the bot owner's Discord user ID. The owner can use /setup and
# /settings even without server-admin permission. Set BOT_OWNER_ID_HASH in
# .env to override at runtime.
OWNER_ID_HASH = os.environ.get(
    "BOT_OWNER_ID_HASH",
    "cdf08c90c25d49f98110d9b7362823aa0032437b48e5a6b64b73f66b61963053",
)

DEFAULT_CURRENCY = "credits"
DEFAULT_BALANCE = 1000

SHARE_PAYOUT = 100
DEFAULT_SUBSIDY = 5000

TRADE_COOLDOWN_SECONDS = 600
INFLATION_CHECK_INTERVAL = 3600
