"""
Configuration centralisée pour prospect-pro.
Gère Gemini + Groq fallback, logging, timeouts.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("prospect")

# ============================================================
# API KEYS
# ============================================================

PLACES_API_KEY = os.getenv("PLACES_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

if not PLACES_API_KEY:
    logger.warning("⚠️  PLACES_API_KEY non configurée")
if not GEMINI_API_KEY and not GROQ_API_KEY:
    logger.warning("⚠️  Ni GEMINI_API_KEY ni GROQ_API_KEY configurés")

GEMINI_MODEL = "gemini-3.6-flash"  # Modèle Gemini actif
GROQ_MODEL = "openai/gpt-oss-120b"  # Fallback performant Groq
GROQ_MODELS_FALLBACK = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]

# ============================================================
# PLAYWRIGHT CONFIG
# ============================================================

PLAYWRIGHT_HEADLESS = True  # À override via UI Streamlit
PLAYWRIGHT_TIMEOUT_MS = 60000  # 60s max par page
PLAYWRIGHT_RETRY_MAX = 3
PLAYWRIGHT_RETRY_DELAY_SEC = 2

# Chrome/Chromium arguments pour éviter les bans
PLAYWRIGHT_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--no-first-run",
    "--disable-blink-features=AutomationControlled",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ============================================================
# DATABASE
# ============================================================

DB_PATH = os.getenv("DB_PATH", "prospection.db")

# ============================================================
# SCRAPING SELECTORS (résilients)
# ============================================================

MAPS_SELECTORS = {
    "cookie_accept": [
        "button:has-text('Accept all')",
        "button:has-text('Tout accepter')",
        "button[aria-label*='Accept']",
    ],
    "place_link": ["a.hfpxzc"],
    "reviews_tab": [
        "button[role='tab']:has-text('Avis')",
        "button[role='tab']:has-text('Reviews')",
        "div[role='tab']:has-text('Avis')",
    ],
    "scrollable_area": [
        "div.m6R6yc",
        "div[role='main']",
        "div.review-dialog-list",
    ],
    "review_blocks": ["div.jftiEf"],
    "phone_button": [
        "button[data-item-id='phone']",
        "a[data-item-id='phone']",
    ],
    "website_link": [
        "a[data-item-id^='authority']",
        "a[aria-label*='Site web']",
        "a[data-tooltip*='Site web']",
    ],
    "address_element": ["button[data-item-id='address']", "a[data-item-id='address']"],
}

# ============================================================
# SCORING THRESHOLDS
# ============================================================

SCORE_CHAUD = 70  # 🔥 CHAUD
SCORE_TIEDE = 40  # 🌡️ TIÈDE
# < 40 = ❄️ FROID

# ============================================================
# UTILITIES
# ============================================================


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger configuré."""
    return logging.getLogger(f"prospect.{name}")
