# ============================================================
# config.py - bot control panel
# purpose:  all trading parametres live here. To change how 
# the bot behaves, you change values in this file only. The 
# rest of the bot reads from here.
# author:   perpgremlin-
# date:     march 2026
# ============================================================


# ------------------------------------------------------------
# INSTRUMENT SETTINGS
# ------------------------------------------------------------

# the trading pair we are trading
SYMBOL = "SOLUSDT"

# the market category on bybit
# "linear" means USDT-settled perpetual futures
CATEGORY = "linear"

# leverage multiplier applied to the position
# 3x means every $1 of margin controls $3 of position
LEVERAGE = 3


# ------------------------------------------------------------
# MARTINGALE ENTRY SETTINGS
# ------------------------------------------------------------

# size of the very first order in usdt
# this is the smallest order the bot will place
# all subsequent levels are multiples of this value
INITIAL_ORDER_SIZE = 100

# multiplier added to order at each level
# 2.0 = pure martingale (order size doubles every level)
# level 1: $100, level 2: $200, level 3 = $400, level 4 = 800
MARTINGALE_MULTIPLIER = 2.0

# maximum number of levels before the bot stops placing orders
# at level 4 the bot holds all and waits - no more entries
MAX_LEVELS = 4

# percentage drop between each martingale level
# 0.236 = 23.6% - the fist fibonacci level above 18
# each new level triggers when price drops 23.6% from previous
LEVEL_SPACING_PCT = 0.236


# ------------------------------------------------------------
# EXIT SETTINGS
# ------------------------------------------------------------

# fibonacci extension levels above the level 1 anchor price
# these are the three staged exits
# 1.618 = 61.8% above L1 entry (the golden ratio)
# 2.0   = 100% above L1 entry (a full double)
# 2.618 = 161.8% above L1 entry ( the big extension)
EXIT_LEVELS = [1.618, 2.0, 2.618]

# percentage of total position to close at each stage
# 0.25 = 25% - three exits of 25% leaves 25% as the moonbag
EXIT_SIZE_PCT = 0.25

# trailing stop distance on the moonbag as a percentage
# 0.10 = 10% - if price drops 10% from its peak, moonbag closes
TRAILING_STOP_PCT = 0.10


# ------------------------------------------------------------
# MARGIN SAFETY SETTINGS
# ------------------------------------------------------------

# MMR threshold at which the bot sends a telegram warning
# 0.55 = 55% - early warning that margin is getting thin
MMR_WARNING_THRESHOLD = 0.55

#MMR threshold at which the bot stops placing new orders
# 0.65 = 65% - bot holds existion position but adds nothing new
MMR_STOP_THRESHOLD = 0.65

# maximum number of re-entry ladders the bot will spawn
# after price retraces below average entry
# once this limit is hit the bot holds and waits
MAX_REENTRY_LADDERS = 3


# ------------------------------------------------------------
# ALERT SETTINGS
# ------------------------------------------------------------

# how often the bo sends a heartbeat messgae to telegram
# confirming it is alive and running normally
# 43200 seconds = 12 hours
HEARTBEAT_INTERVAL_SECONDS = 43200

# how often the bot sends daily PnL summary to telegram
# 86400  seconds = 24 hours
PNL_SUMMARY_INTERVAL_SECONDS = 86400

# funding rate threshold that triggers a telegram alert
# 0.001 = 0.1% - significant funding event worth knowing about
FUNDING_RATE_ALERT_THRESHOLD = 0.001

# ------------------------------------------------------------
# RISK MANAGEMENT SETTINGS
# ------------------------------------------------------------

# VOLATILITY PAUSE - disabled, martingale strategy benefits
# from buying sharp dips rather than pausing during them
# uncomment and implement in bot.py if behaviour changes

# VOLATILITY_PAUSE_PCT = 0.10
# VOLATILITY PAUSE SECONDS = 3600

# DAILY_LOSS_LIMIT_USDT - disabled, martingale strategies
# often sit deep underwater waiting for mean reversion
# maximum unrealised loss in USDT before the bot pauses
# and sends a telegram alert for manual review
# this is seperate from MMR protection

# DAILY_LOSS_LIMIT_USDT = 500



# ------------------------------------------------------------
# ANCHOR RESET SETTINGS
# ------------------------------------------------------------

# number of levels that must fill rapidly to trigger an
# anchor reset - bot detects crash and restructures
# 2 = if 2 or more levels fill, evaluate the anchor reset
ANCHOR_RESET_TRIGGER_LEVELS = 2

# time window in seconds to detect rapid fill levels
# if ANCHOR_RESET_TRIGGER_LEVELS fill within this window
# the anchor reset logic fires
# 3600 = 1 hour
RAPID_FILL_WINDOW_SECONDS = 3600

# MMR threshold that activates margin safety mode
# during an anchor reset - matches our main MMR stop
# 0.65 = 65%
MARGIN_SAFETY_MMR = 0.65

# if margin safety mode activates, the bot consolidates
# remaining margin into one averaging order placed here
# below the new anchor - matches our standard level spacing
# 0.236 = 23.6% below new anchor
SAFETY_ORDER_SPACING_PCT = 0.236


# ------------------------------------------------------------
# API SETTINGS
# ------------------------------------------------------------

# number of times the bot retries a failed API call
# before sending a telegram alert and pausing
API_RETRY_ATTEMPTS = 3

# seconds between each retry attempt
# doubles each time - 2s, 4s, 8s (exponential backoff)
API_RETRY_DELAY_SECONDS = 2

# how often the main bot loop runs in seconds
# 60 = bot checks the market and its orders every 60 seconds
LOOP_INTERVAL_SECONDS = 60


# ------------------------------------------------------------
# LOGGING SETTINGS
# ------------------------------------------------------------

# path to the log file where the bot records all activity
# every order, every decision, every error gets written here
LOG_FILE = "logs/martingale_bot.log"

# logging level - controls how much detail gets written
# INFO = normal running, records important events only
# DEBUG = records everything, use when troubleshooting
LOG_LEVEL = "INFO"

