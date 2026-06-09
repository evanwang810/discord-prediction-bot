import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DB_PATH = ROOT / "bot.db"
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "1256766984968995010"))

DEFAULT_CURRENCY = "credits"
DEFAULT_BALANCE = 1000

SHARE_PAYOUT = 100
DEFAULT_SUBSIDY = 5000

TRADE_COOLDOWN_SECONDS = 600
INFLATION_CHECK_INTERVAL = 3600
