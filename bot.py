# bot.py
# ============================================================
# MARTINGALE BOT — MAIN FILE
# this is the brain of the bot. all trading logic lives here.
# it reads its settings from config.py and credentials from 
# .env - never hardcoded in this file.
# author:   perpgremlin- 
# date:     april 2026
# ============================================================


# ------------------------------------------------------------
# IMPORTS
# all of the libraries this bot needs to function
# ------------------------------------------------------------

# pybit - official Bybit python SDK
# habdles all commun nication with Bybits server
from pybit.unified_trading import HTTP

# load dot_env - reads our .env file and loads the keys
# into memory so python can access them via os.getenv()
from dotenv import load_dotenv

# os - built in python library
# lets us read environment variables loaded by dotenv
import os

# logging - built in pythhon library
# let the bot write an activity diary to a log file
import logging

# requests - send HTTP requests
# we use this to send telegram alert messages
import requests

# time - built in python library
# let the bot pause between actions using time.sleep()
import time

# config - our own config.py file
# imports all our trading parametres
import config

# json is the format used to build the bot's memory
# standard way of storing structured data as plain text
# it survives crashes and restarts
import json


# ------------------------------------------------------------
# ENVIRONMENT SETUP
# load the. env file and read our credentials into variables
# ------------------------------------------------------------

# this reads the ,env file and makes its contents available
# to python - must be called before any os.getenv() calls
load_dotenv()

# read each credential from the environment into a variable
#os.getenv() looks up the value by its key name in .env
API_KEY     = os.getenv('BYBIT_API_KEY')
API_SECRET  = os.getenv('BYBIT_API_SECRET')
TESTNET     = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
TG_TOKEN    = os.getenv('TELEGRAM_BOT_TOKEN')
TG_CHAT_ID  = os.getenv('TELEGRAM_CHAT_ID')


# ------------------------------------------------------------
# LOGGING SETUP
# configures the bot to write an activity diary to a file
# every important action, order and error gets recorded here
# ------------------------------------------------------------

# basicConfigs sets up the logging system with our preferences
logging.basicConfig(
    # where to write the log file - defined in config.py
    filename=config.LOG_FILE,
    # what level of detail to record - defined in config.py
    level=getattr(logging, config.LOG_LEVEL),
    # the format of each log line:
    # timestamp - severity level - message
    format='%(asctime)s - %(levelname)s - %(message)s',
    # keep appending to the log file, never overwrite it
    filemode='a'
)

# also print log messages to the terminal so we can watch
# the bot running in real time as well as reading the file
console = logging.StreamHandler()
console.setLevel(getattr(logging, config.LOG_LEVEL))
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# first log entry - confirms the bot has started
logging.info('Martingale bot starting up')

# ------------------------------------------------------------
# TELEGRAM ALERT FUNCTION
# sends a message to your telegram chat
# called whenever the bot needs to notify you of something
# ------------------------------------------------------------

def send_telegram(message):
    # build the URL for telegram's API endpoint
    # this is the address we send our message to
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

    # the data we are sending - who to and what to say
    payload = {
        'chat_id': TG_CHAT_ID,
        'text': message
    }

    try:
        # send the msg via HTTP POST request
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.urlopen(url, data=data, timeout=10)
        response_code = req.getcode()
        # log wether it succeeded or failed
        if response_code == 200:
            logging.info(f'Telegram alert send: {message}')
        else:
            logging.error(f'Telegram alert failed: {response.status_code}')

    except Exception as e:
        # if something goes wrong, log the error
        # but do not crash the bot - alerts are not critical
        logging.error(f'Telegram alert error: {e}')


# ------------------------------------------------------------
# BYBIT CONNECTION
# creates a live session with bybit's API
# all order placement and account queries go through this
# ------------------------------------------------------------

# HTTP() creates the connection session
# testnet=TESTNET means it reads our .env value - 
# if BYBIT_TESTNET=true it connects to the testnet (fake money)
# if BYBIT_TESTNET=false it connects to live (real money)
session = HTTP(
    testnet=TESTNET,
    api_key=API_KEY,
    api_secret=API_SECRET
)

logging.info('Bybit session created successfully')


# ------------------------------------------------------------
# CONNECTION TEST
# fetches the current SOL price to verify the connection
# works before we attempt any trading logic
# ------------------------------------------------------------

def test_connection():
    try:
        # ask Bybit for the current SOL price
        response = session.get_tickers(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        # extract the last traded price from the response
        price = response['result']['list'][0]['lastPrice']

        # log and alert the connection is working
        logging.info(f'Connection test passed - {config.SYMBOL} price: ${price}')
        send_telegram(f'Martingale bot online. {config.SYMBOL} price: ${price}')

    except Exception as e:
        # if the connection fails, log the error and alert
        logging.error(f'Connection test failed: {e}')
        send_telegram(f'Martingale bot failed to connect: {e}')


# ------------------------------------------------------------
# SET LEVERAGE
# tells Bybit to use our configured leverage on SOLUSDT
# this runs once on startup before any orders are placed
# ------------------------------------------------------------

def set_leverage():
    try:
        # set both buy and sell leverage to our configured value
        # on linear perpetuals Bybit requires both to be set
        session.set_leverage(
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            buyLeverage=str(config.LEVERAGE),
            sellLeverage=str(config.LEVERAGE)
        )

        logging.info(f'Leverage set to {config.LEVERAGE}x on {config.SYMBOL}')
        send_telegram(f'Leverage set to {config.LEVERAGE}x on {config.SYMBOL}')

    except Exception as e:
        # bybit throws an error if leverage is already set
        # to the same value — this is normal, not a problem
        logging.info(f'Leverage already set or minor error: {e}')


# ------------------------------------------------------------
# STATE MANAGEMENT
# loads and saves the bot's memory to state.json
# tracks things bybit doesnt know about - anchor price,
# ladder number, and how many re-entries have happened
# ------------------------------------------------------------

def load_state():
    # default state - what the bot looks like with no history
    default_state = {
        'anchor_price': None,       # price where L1 was placed
        'current_level': 0,         # how many levels are filled
        'reentry_count': 0,         # how many re-entry ladders spawned
        'active_orders': [],        # list of all open order IDs
        'average_entry': None,      # current average entry price
        'cycle_active': False,      # is a ladder already running
        'moonbag_active': False,    # is the moonbag trailing stop active
        'highest_price': None,      # highest price seen during moonbag
    }


    try:
        # check if state.json exists and has content
        if os.path.exists('state.json') and os.path.getsize('state.json') > 0:
            with open('state.json', 'r') as f:
                state = json.load(f)
                logging.info('State loaded from state.json')
                return state
        else: 
            # no state file found - fresh start
            logging.info('No state file found - starting fresh')
            return default_state
        
    except Exception as e:
        logging.error(f'Error loading state: {e}')
        return default_state


def save_state(state):
    try:
        with open('state.json', 'w') as f:
            json.dump(state, f, indent=4)
            logging.info('State saved to state.json')

    except Exception as e:
        logging.error(f'Error saving state: {e}')


# ------------------------------------------------------------
# BYBIT STATE CROSS REFERENCE
# queries bybit for open positions and orders on startup
# cross references against state.json to ensure they match
# if they differ, bybit is always treated as the truth
# ------------------------------------------------------------

def reconcile_state(state):
    try:
        # query bybit for any open positions on SOLUSDT
        position_response = session.get_positions(
            category=config.CATEGORY, 
            symbol=config.SYMBOL
        )

        # query bybit for any open orders on SOLUSDT
        order_response = session.get_open_orders(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        # extract the position list from the response
        positions = position_response['result']['list']

        # extract the position list from the response
        orders = order_response['result']['list']

        # check if bybit shows and active positiion
        bybit_has_position = any(
            float(p['size']) > 0 for p in positions
        )

        # check if bybit shows any open orders
        bybit_has_orders = len(orders) > 0

        # if bybit shows a position but state says no cycle
        # trust bybit and update state accordingly
        if bybit_has_position and not state['cycle_active']:
            logging.warning('Bybit shows open position but state says no cycle - updating state')
            state['cycle_active'] = True

        # if bybit shows no position but state says cycle active
        # trust bybit and reset state
        if not bybit_has_position and state['cycle_active']:
            logging.warning('Bybit shows no positions but state says cycle active - resetting state')
            state['cycle_active'] = False
            state['current_level'] = 0
            state['average_entry'] = None

        # update active orders in state from bybit's live data
        state['active_orders'] = [o['orderId'] for o in orders]

        logging.info(f'State reconciled - position: {bybit_has_position}, open orders: {len(orders)}')
        send_telegram(f'State reconciled - position active: {bybit_has_position}, open orders: {len(orders)}')
        
        return state
        
    except Exception as e:
        logging.error(f'Error reconciling state: {e}')
        return state


# ------------------------------------------------------------
# FIBONACCI CALCULATOR
# takes an anchor price and calculates all entry and exit
# levels based on the risk model parametres in config.py
# this is the mechanical heart of the bot
# ------------------------------------------------------------

def calculate_levels(anchor_price):
    # calculate the four martingale entry prices
    # each level is 23.6% below the previous one
    entry_levels = []
    for i in range(config.MAX_LEVELS):
        level_price = anchor_price * (1 - config.LEVEL_SPACING_PCT) ** i
        entry_levels.append(round(level_price, 4))

    # calculate the three staged exit prices
    # each is a fibonaci extention above the anchor price
    exit_levels = []
    for multiplier in config.EXIT_LEVELS:
        exit_price = anchor_price * multiplier
        exit_levels.append(round(exit_price, 4))

    # log the calculated levels so we can verify them
    logging.info(f'Anchor price: {anchor_price}')
    logging.info(f'Entry levels: {entry_levels}')
    logging.info(f'Exit levels: {exit_levels}')
    return {
        'entry_levels': entry_levels,
        'exit_levels': exit_levels
    }


# ------------------------------------------------------------
# MMR CHECKER
# checks current margin ratio before placing any order
# if mmr is too high, the order is skipped to protect margin
# ------------------------------------------------------------

def check_mmr():
    try:
        # query bybit for current account margin information
        response = session.get_wallet_balance(
            accountType="UNIFIED"
        )

        # extract the margin ratio from the response
        # bybit returns this as a string so we convert it to float
        mmr = float(response['result']['list'][0]['accountMMRate'])

        logging.info(f'Current MMR: {mmr:.2%}')

        # check against our warning threshold
        if mmr >= config.MMR_WARNING_THRESHOLD:
            logging.warning(f'MMR warning threshold reached: {mmr:.2%}')
            send_telegram(f'Warning - MMR at {mmr:.2%}. Approaching order stop threshold.')

        # check against our hard stop threshold
        if mmr >= config.MMR_STOP_THRESHOLD:
            logging.warning(f'MMR stop threshold reached: {mmr:.2%} - no new orders will be placed.')
            send_telegram(f'MARGIN SAFETY - MMR at {mmr:.2%}. Bot pausing new orders.')
            return False

        # mmr is safe - okay to place orders
        return True

    except Exception as e:
        logging.error(f'Error checking MMR: {e}')
        # if we can't check mmr, do not place orders
        # safer to skip than to risk margin
        return False


# ------------------------------------------------------------
# order placement
# places a single limit order on bybit
# checks for duplicates before producing to prevent
# accidentally placing the same order twice
# ------------------------------------------------------------

def place_order(symbol, side, qty, price, order_tag):
    try:
        # check mmr is safe before placing any order
        if not check_mmr():
            logging.warning(f'Order skipped - MMR too high: {order_tag}')
            return None

        # check if an order at this price already exists
        # this prevents duplicate orders on the same level
        open_orders = session.get_open_orders(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        for order in open_orders['result']['list']:
            if float(order['price']) == float(price):
                logging.info(f'Duplicate order detected at {price} - skipping')
                return None

        # place the limit order on bybit
        response = session.place_order(
            category=config.CATEGORY,
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=str(price),
            timeInForce="PostOnly",
            orderLinkId=order_tag
        )

        # check if the order was accepted
        if response['retCode'] == 0:
            order_id = response['result']['orderId']
            logging.info(f'Order placed - {side} {qty} {symbol} at {price} - ID: {order_id}')
            send_telegram(f'Order placed - {side} {qty} {symbol} at ${price}')
            return order_id
        else:
            logging.error(f'Order failed {response["retMsg"]}')
            send_telegram(f'Order failed {response["retMsg"]}')
            return None
    
    except Exception as e:
        logging.error(f'Error placing order: {e}')
        send_telegram(f'Error placing order: {e}')
        return None


# ------------------------------------------------------------
# MAIN ENTRY POINT
# this is what runs when you execute: python3 bot.py
# ------------------------------------------------------------

if __name__ == '__main__':
    # run the connection test first
    # if this fails, something is wrong before we even start
    test_connection()
    set_leverage()
    state = load_state()
    state = reconcile_state(state)
    save_state(state)
    logging.info(f'Bot state loaded - cycle active: {state["cycle_active"]}, level: {state["current_level"]}')
    send_telegram(f'Bot state loaded - cycle active: {state["cycle_active"]}, level: {state["current_level"]}')
    mmr_safe = check_mmr()
    print(f'MMR safe to trade: {mmr_safe}')
    test_order = place_order(
        symbol=config.SYMBOL,
        side="Buy",
        qty=1,
        price=50.00,
        order_tag="test_order_001"
    )
print(f'Order result: {test_order}')

