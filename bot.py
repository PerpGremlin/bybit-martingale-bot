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
# MAIN ENTRY POINT
# this is what runs when you execute: python3 bot.py
# ------------------------------------------------------------

if __name__ == '__main__':
    # run the connection test first
    # if this fails, something is wrong before we even start
    test_connection()

