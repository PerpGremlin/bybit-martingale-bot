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
        'exit_order_tags': {}       # so we dont get errors from incorrect tags
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

        if bybit_has_position:
            for p in position:
                if float(p['size']) > 0:
                    live_avg_entry = float(p['avgPrice'])
                    state['average_entry'] = live_avg_entry
                    logging.info(f'Average entry synced from Bybit: ${live_avg_entry}')
                    # if anchor is missing or stale, set it from average entry
                    if state ['anchor_price'] is None:
                        state['anchor_price'] = live_avg_entry
                        logging.info(f'Anchor price set from average entry: ${live_avg_entry}')
                    break

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
# ORDER PLACEMENT
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
            timeInForce="GTC",
            orderLinkId=order_tag,
            positionIdx=1
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
# ENTRY LOGIC
# decides when to place each martingale level
# compares current price to calculated entry levels
# only places an order if the level hasnnt been filled yet
# ------------------------------------------------------------

def run_entry_logic(state, levels):
    try:
        # get the current SOL price from bybit
        response = session.get_tickers(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        current_price = float(response['result']['list'][0]['lastPrice'])
        logging.info(f'Current price: {current_price}')

        # if no cycle is active, place the first level order
        if not state['cycle_active']:
            logging.info('No active cycle - placing L1 order')
            anchor_price = current_price
            state['anchor_price'] = anchor_price
            levels = calculate_levels(anchor_price)

            # place L1 order at current price
            order_tag = f'martingale_L1_{anchor_price}_{int(time.time())}'
            order_id = place_order(
                symbol=config.SYMBOL,
                side="Buy",
                qty=max(round(config.INITIAL_ORDER_SIZE / anchor_price, 1), 0.1),
                price=anchor_price,
                order_tag=order_tag
            )

            if order_id:
                state['cycle_active'] = True
                state['current_level'] = 1
                state['active_orders'].append(order_id)

            return state, levels

        # if cycle is active, check if we need to place more levels
        # loop through each entry level
        for i, entry_price in enumerate(levels['entry_levels']):
            level_num = i + 1

            # skip levels already filled
            if level_num <= state['current_level']:
                continue

            # is current price is at or below this level
            # and we havent placed this order yet, place it
            if current_price <= entry_price:
                order_tag = f'martingale_L{level_num}_{entry_price}_{int(time.time())}'
                qty = (config.INITIAL_ORDER_SIZE * (config.MARTINGALE_MULTIPLIER ** i)) / entry_price

                order_id = place_order(
                    symbol=config.SYMBOL,
                    side="Buy",
                    qty=max(round(qty, 1), 0.1),
                    price=entry_price,
                    order_tag=order_tag
                )

                if order_id:
                    state['current_level'] = level_num
                    state['active_orders'].append(order_id)
                    save_state(state)
                    
        return state, levels

    except Exception as e:
        logging.error(f'Error in entry logic: {e}')
        return state, levels


# ------------------------------------------------------------
# EXIT LOGIC
# monitors the position and places staged exit orders
# closes 25% at each fibonnaci extension level
# final 25% becomes the moonbag with a trailing stop
# ------------------------------------------------------------

def run_exit_logic(state, levels):
    try:
        # get current price
        response = session.get_tickers(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        current_price = float(response['result']['list'][0]['lastPrice'])

        # get current position size from bybit
        position_response = session.get_positions(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        positions = position_response['result']['list']

        # find our open long position
        position_size = 0
        for p in positions:
            if float(p['size']) > 0:
                position_size = float(p['size'])
                avg_entry = float(p['avgPrice'])
                state['average_entry'] = avg_entry
                break

        # if no position exists, nothing to exit
        if position_size == 0:
            return state

        # calculate exit quantity - 25% of total position
        # make sure the exit qty meets minimum order size
        exit_qty = max(round(position_size * config.EXIT_SIZE_PCT, 1), 0.1)

        # check each exit level
        for i, exit_price in enumerate(levels['exit_levels']):
            # check if we already have a tag for this exit level
            # reuse existing tag if we do, generate new one if not
            tag_key = f'exit_L{i+1}'
            if tag_key in state['exit_order_tags']:
                order_tag = state['exit_order_tags'][tag_key]
            else:
                order_tag = f'exit_L{i+1}_{exit_price}_{int(time.time())}'
                state['exit_order_tags'][tag_key] = order_tag
                save_state(state)

            # check if this exit order already exists
            open_orders = session.get_open_orders(
                category=config.CATEGORY,
                symbol=config.SYMBOL
            )
            existing_tags = [o['orderLinkId'] for o in open_orders['result']['list']]
            if order_tag not in existing_tags:
                # refresh position size before placing exit order
                # skip if position has been reduced to zero
                position_response = session.get_positions(
                    category=config.CATEGORY,
                    symbol=config.SYMBOL
                )
                positions = position_response['result']['list']
                current_size = 0
                for p in positions:
                    if float(p['size']) > 0 and p['side'] == 'Buy':
                        current_size = float(p['size'])
                if current_size == 0:
                    logging.info('No position remaining - skipping exit order')
                    break
                # place the exit order
                order_id = place_order(
                    symbol=config.SYMBOL,
                    side="Sell",
                    qty=exit_qty,
                    price=exit_price,
                    order_tag=order_tag
                )
                # if order failed clear the stored tag
                # so a fresh one is generated next loop
                if order_id is None:
                    state['exit_order_tags'].pop(tag_key, None)
                    save_state(state)

        # handle moonbag trailing stop
        if state['moonbag_active']:
            # update highest price seen
            if state['highest_price'] is None or current_price > state['highest_price']:
                state['highest_price'] = current_price
                save_state(state)

            # check if price has dropped 10% from highest
            trailing_stop_price = state['highest_price'] * (1 - config.TRAILING_STOP_PCT)

            if current_price <= trailing_stop_price:
                logging.info(f'Trailing stop triggered at {current_price}')
                send_telegram(f'Moonbag trailing stop triggeres at ${current_price} - closing position')

                # close remaining position at market
                session.place_order(
                    category=config.CATEGORY,
                    symbol=config.SYMBOL,
                    side="Sell",
                    orderType="Market",
                    qty=str(position_size),
                    reduceOnly=True
                )
                # reset state after full cycle complete
                state['cycle_active'] = False
                state['current_level'] = 0
                state['anchor_price'] = None
                state['average_entry'] = None
                state['moonbag_active'] = False
                state['highest_price'] = None
                save_state(state)

        return state

    except Exception as e:
        logging.error(f'Error in exit logic: {e}')
        return state

# ------------------------------------------------------------
# ANCHOR RESET
# detects rapid multi-level fills and restructures the ladder
# if 2 or more levels fill within the rapid fill window, 
# the anchor is moved to a new average entry price
# and all exit targets are recalculated from there
# ------------------------------------------------------------

def check_anchor_reset(state, levels):
    try:
        # query bybit for recently filled orders
        response = session.get_order_history(
            category=config.CATEGORY,
            symbol=config.SYMBOL,
            limit=20
        )

        orders = response['result']['list']

        # get current time in seconds
        now = time.time()

        # count how many martingale entry orders filled
        # within the rapid fill window
        recent_fills = []
        for order in orders:
            # only look at our martingale entry orders
            if 'martingale_L' not in order.get('orderLinkId', ''):
                continue
            # only look at filled orders
            if order['orderStatus'] != 'Filled':
                continue
            # convert bybit timestamp from milliseconds to seconds
            fill_time = int(order['updatedTime']) / 1000
            # check if this fill happened within our window
            if now - fill_time <= config.RAPID_FILL_WINDOW_SECONDS:
                recent_fills.append(order)

        # if fewer than trigger threshold filled recently
        # no reset needed
        if len(recent_fills) < config.ANCHOR_RESET_TRIGGER_LEVELS:
            return state, levels

        # rapid fill detected - log and alert
        logging.warning(f'Rapid fill detected - {len(recent_fills)} levels filled quickly')
        send_telegram(f'Anchor reset triggered - {len(recent_fills)} levels filled rapidly. Restructuring ladder.')

        # query current position for new average entry
        position_response = session.get_positions(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        positions = position_response['result']['list']

        new_avg_entry = None
        for p in positions:
            if float(p['size']) > 0:
                new_avg_entry = float(p['avgPrice'])
                break

        if new_avg_entry is None:
            logging.warning('Anchor reset triggered but no open position found')
            return state, levels

        # set new anchor just below average entry
        new_anchor = round(new_avg_entry * (1 - config.SAFETY_ORDER_SPACING_PCT), 4)
        logging.info(f'New anchor set at {new_anchor} - avg entry was {new_avg_entry}')

        # recalculate all levels from new anchor
        levels = calculate_levels(new_anchor)
        state['anchor_price'] = new_anchor

        # check mmr before placing safety order
        if not check_mmr():
            logging.warning('MMR too high after anchor reset - holding, no safety order placed')
            send_telegram('Anchor reset complete - MMR too high to place safety order. Holding position.')
            save_state(state)
            return state, levels

        # place consolidated safety order at 23.6% below new anchor
        safety_price = levels['entry_levels'][1]
        safety_qty = round(
            (config.INITIAL_ORDER_SIZE * config.MARTINGALE_MULTIPLIER) / safety_price, 1
        )

        order_id = place_order(
            symbol=config.SYMBOL,
            side='Buy',
            qty=safety_qty,
            price=safety_price,
            order_tag=f'safety_order_{safety_price}'
        )

        if order_id:
            state['active_orders'].append(order_id)
            save_state(state)
            send_telegram(f'Safety order placed at ${safety_price} after anchor reset')

        return state, levels

    except Exception as e:
        logging.error(f'Error in anchor reset: {e}')
        return state, levels

# ------------------------------------------------------------
# RE-ENTRY LOGIC
# monitors average entry price after partial exits     
# if price drops below average entry, cancels remaining
# exit orders and spawns a fresh ladder from the new anchor
# only fires if re-entry count is below maximum
# ------------------------------------------------------------

def run_reentry_logic(state, levels):
    try:
        # only run if a cycle is active
        if not state['cycle_active']:
            return state, levels

        # only run if we have an average entry to compare against
        if state['average_entry'] is None:
            return state, levels
        # check if we have hit the re-entry limit
        if state['reentry_count'] >= config.MAX_REENTRY_LADDERS:
            logging.info('Max re-entry ladders reached - holding position')
            return state, levels

        # get current price
        response = session.get_tickers(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        current_price = float(response['result']['list'][0]['lastPrice'])

        # if price is above average entry, nothing to do
        if current_price >= state['average_entry']:
            return state, levels

        # price is below average entry - re-entry triggered
        logging.warning(f'Price {current_price} below average entry {state["average_entry"]} - re-entry triggered')
        send_telegram(f're-entry triggered - price ${current_price} below average entry ${state["average_entry"]}. Spawning new ladder.')

        # cancel all open exit orders
        open_orders = session.get_open_orders(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )

        for order in open_orders['result']['list']:
            # only cancel exit orders, not entry orders
            if 'exit_L' in order.get('orderLinkId', ''):
                session.cancel_order(
                    category=config.CATEGORY,
                    symbol=config.SYMBOL,
                    orderId=order['orderId']
                )
                logging.info(f'Cancelled exit order: {order["orderId"]}')

        # set new anchor just below current average entry
        new_anchor = round(current_price * (1 - config.LEVEL_SPACING_PCT), 4)
        logging.info(f'New re-entry anchor set at {new_anchor}')

        # recalculate all levels from new anchor
        levels = calculate_levels(new_anchor)
        state['anchor_price'] = new_anchor
        state['reentry_count'] += 1

        logging.info(f'Re-entry ladder {state["reentry_count"]} of {config.MAX_REENTRY_LADDERS}')
        send_telegram(f'New ladder spawned from ${new_anchor} - re-entry {state["reentry_count"]} of {config.MAX_REENTRY_LADDERS}')

        save_state(state)
        return state, levels

    except Exception as e:
        logging.error(f'Error in re-entry logic: {e}')
        return state, levels

# ------------------------------------------------------------
# API RETRY WRAPPER
# wraps api calls in retry logic with exponential backoff
# if a call fails itwaits and tries again up to 3 times
# if all retries fail it alerts via telegram and returns none
# ------------------------------------------------------------

def api_calls_with_retry(func, *args, **kwargs):
    # track how many attempts we have made
    attempts = 0

    while attempts < config.API_RETRY_ATTEMPTS:
        try:
            # attempt the api call
            result = func(*args, **kwargs)
            return result

        except Exception as e:
            attempts += 1
            # calculate wait time - doubles each attempt
            # attempt 1: 2s, attempt 2: 4s, attempt 3: 8s
            wait_time = config.API_RETRY_DELAY_SECONDS * (2 ** (attempts - 1))

            logging.warning(f'API call failed (attempt {attempts} of {config.API_RETRY_ATTEMPTS}): {e}')

            # if we have used all attempts, alert and give up.
            if attempts >= config.API_RETRY_ATTEMPTS:
                logging.error(f'API call failed after {config.API_RETRY_ATTEMPTS} attempts - giving up')
                send_telegram(f'API unreachable after {config.API_RETRY_ATTEMPTS} attempts. Bot pausing. Check connection.')
                return None

            # wait before trying again
            logging.info(f'Retrying in {wait_time} seconds...')
            time.sleep(wait_time)

    return None


# ------------------------------------------------------------
# MAIN LOOP
# the heartbeat of the bot - runs every 6 seconds
# calls every function in the sequence on each iteration
# this is what makes the bot run continuously
# ------------------------------------------------------------

def run_bot():
    # load state and reconcile with bybit on startup
    state = load_state()
    state = reconcile_state(state)
    save_state(state)

    # calculate initial levels from anchor if cycle is active
    # otherwise levels will be set when first order is placed
    if state['cycle_active'] and state['anchor_price'] is None:
        state, levels = cold_start_recovery(state)
    elif state['anchor_price']:
        levels = calculate_levels(state['anchor_price'])
    else:
        levels = {'entry_levels': [], 'exit_levels': []}

    # track time for heartbeat and pnl summary
    last_heartbeat = time.time()
    last_pnl_summary = time.time()

    logging.info('Main loop starting')
    send_telegram('Martingale bot main loop started - Monitoring market')

    # main loop - runs forever until manually stopped
    while True:
        try:
            # run entry logic - checks if new orders need placing
            state, levels = run_entry_logic(state, levels)

            # run exit logic - checks if exit orders need placing
            # and manages the moonbag trailing stop
            state = run_exit_logic(state, levels)

            # check for rapid fills and restructure if needed
            state, levels = check_anchor_reset(state, levels)

            # check if re-erntry ladder needed
            state, levels = run_reentry_logic(state, levels)

            # heartbeat - send telegram every 12 hours
            now = time.time()
            if now - last_heartbeat >= config.HEARTBEAT_INTERVAL_SECONDS:
                logging.info('Heartbeat - bot is alive')
                send_telegram('Heartbeat - martingale bot running normally')
                last_heartbeat = now

            # pnl summary - send telegram every 24 hours
            if now - last_pnl_summary >= config.PNL_SUMMARY_INTERVAL_SECONDS:
                # query wallet for current balance
                wallet = session.get_wallet_balance(accountType="UNIFIED")
                balance = wallet['result']['list'][0]['totalWalletBalance']
                upnl = wallet['result']['list'][0]['totalPerpUpl']
                logging.info(f'Daily PnL summary - balance: {balance}, uPnL: {upnl}')
                send_telegram(f' Daily summary - balance ${balance} | unrealised PnL: ${upnl} | level: {state["current_level"]} | re-entries: {state["reentry_count"]}')
                last_pnl_summary = now

            # wait before the next iteration
            logging.info(f'Loop complete - waiting {config.LOOP_INTERVAL_SECONDS} seconds')
            time.sleep(config.LOOP_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            # ctrl+c pressed - shut down cleanly
            logging.info('Bot stopped by user')
            send_telegram('Martingale bot stopped manually')
            break

        except Exception as e:
            # something went wrong - log it and keep running
            logging.error(f'Error in main loop: {e}')
            send_telegram(f'Main loop error: {e} - bot continuing')
            time.sleep(config.LOOP_INTERVAL_SECONDS)


# ------------------------------------------------------------
# COLD START RECOVERY
# fires on startup when an existing position is detected
# rebuilds full ladder context from bybit live data
# so the bot can resume correctly after any restart
# ------------------------------------------------------------

def cold_start_recovery(state):
    try:
        logging.info('Existing position detected - running cold start recovery')
        send_telegram('Existing position detected - rebuilding ladder context from Bybit')

        # query bybit for current position details
        position_response = session.get_positions(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        positions = position_response['result']['list']

        # find your open long position
        position_size = 0
        avg_entry = None
        for p in positions:
            if float(p['size']) > 0:
                position_size = float(p['size'])
                avg_entry = float(p['avgPrice'])
                break

        # if no position is found something is wrong - return state as is
        if avg_entry is None:
            logging.warning('Cold start recovery - no open positions found on bybit')
            return state, {'entry_levels': [], 'exit_levels': []}

        logging.info('Position found - size: {position_size} SOL, avg entry: ${avg_entry}')

        # rebuild anchor price from avg entry
        # we use average entry as the anchor for level calculations
        anchor_price = avg_entry
        state['anchor_price'] = anchor_price
        state['average_entry'] = avg_entry
        state['cycle_active'] = True

        # recalculate all fibonacci levels from recovered anchor
        levels = calculate_levels(anchor_price)

        logging.info(f'Anchor recovered at ${anchor_price}')
        logging.info(f'Entry levels: {levels["entry_levels"]}')
        logging.info(f'Exit levels: {levels["exit_levels"]}')

        # query open orders to determine current level
        order_response = session.get_open_orders(
            category=config.CATEGORY,
            symbol=config.SYMBOL
        )
        open_orders = order_response['result']['list']

        # count how many entry levels are already filled
        # by comparing position size against level order sizes
        level = 1
        cumulative_qty = config.INITIAL_ORDER_SIZE / anchor_price
        while cumulative_qty < position_size and level < config.MAX_LEVELS:
            level += 1
            next_qty = (config.INITIAL_ORDER_SIZE * (config.MARTINGALE_MULTIPLIER ** (level - 1))) / levels['entry_levels'][level - 1]
            cumulative_qty += next_qty

        state['current_level'] = level
        logging.info(f'Recovered to level {level}')

        # update active orders list from bybit
        state['active_orders'] = [o['orderId'] for o in open_orders]

        save_state(state)

        send_telegram(f'Cold start recovery complete - level {level} avg entry ${avg_entry}, position {position_size} SOL')

        return state, levels

    except Exception as e:
        logging.error(f'Error in cold start recovery: {e}')
        return state, {'entry_levels': [], 'exit_levels': []}

# ------------------------------------------------------------
# MAIN ENTRY POINT
# this is what runs when you execute: python3 bot.py
# ------------------------------------------------------------

if __name__ == '__main__':

    # run the connection test first
    # if this fails, something is wrong before we even start
    test_connection()
    set_leverage()
    run_bot()
