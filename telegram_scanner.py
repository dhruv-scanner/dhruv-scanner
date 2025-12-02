# telegram_scanner.py
# Combined Scanner = 
# 1) OLH (9:15–9:45 custom candle)
# 2) HH/LL (last 20 candles) → 30m + 1H
# Sends FULL RESULT TO TELEGRAM

from SmartApi import SmartConnect
import json
import logging
import pyotp
from datetime import datetime, timedelta
import time
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# --------------------------------------
# TELEGRAM DETAILS
# --------------------------------------
TELEGRAM_TOKEN = "8525158801:AAG8hvNuUEi0vkxxbwJj-V88ZBmDhk3H4JM"
TELEGRAM_CHAT_ID = "988823209"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram error:", e)


# --------------------------------------
# LOGIN DETAILS
# --------------------------------------
API_KEY = "yy8XdcLZ"
CLIENT_CODE = "P305906"
MPIN = "2704"
TOTP_SECRET = "KAJ6VL5L34VCWV3AAFKGI555NU"

# LOGIN
obj = SmartConnect(api_key=API_KEY)
totp = pyotp.TOTP(TOTP_SECRET).now()
data = obj.generateSession(CLIENT_CODE, MPIN, totp)
logging.info("Login Successful")

# --------------------------------------
# LOAD TOKENS
# --------------------------------------
with open("nse_tokens.json", "r") as f:
    tokens = json.load(f)

logging.info(f"Loaded tokens: {len(tokens)}")

# --------------------------------------
# 1) OLH (CUSTOM 30-MIN CANDLE 9:15–9:45)
# --------------------------------------
today = datetime.now().strftime("%Y-%m-%d")
FROM_915 = today + " 09:15"
TO_945   = today + " 09:45"

def get_915_945_candle(token):
    params = {
        "exchange": "NSE",
        "symboltoken": token,
        "interval": "THIRTY_MINUTE",
        "fromdate": FROM_915,
        "todate": TO_945
    }

    for _ in range(20):
        try:
            resp = obj.getCandleData(params)
            if resp and resp.get("data"):
                c = resp["data"][0]
                O, H, L = float(c[1]), float(c[2]), float(c[3])
                if O != 0 and H >= O >= L:
                    return O, H, L
        except:
            pass
        time.sleep(1)
    return None


# RESULTS FOR OLH
OL_exact = []
OH_exact = []
OL_near = []
OH_near = []

# RUN OLH SCAN
for symbol, token in tokens.items():
    c = get_915_945_candle(token)
    if c is None:
        continue
    O, H, L = c

    if O == L:
        OL_exact.append(symbol)
    if O == H:
        OH_exact.append(symbol)

    if abs(O - L) <= 1 and O != L:
        OL_near.append(symbol)
    if abs(O - H) <= 1 and O != H:
        OH_near.append(symbol)


# --------------------------------------
# 2) HH / LL — last 20 candles (30m + 1H)
# --------------------------------------
LOOKBACK_DAYS = 5
TOL = 1.0

def fetch_last_candles(symbol_token, interval):
    start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d") + " 09:00"
    end   = datetime.now().strftime("%Y-%m-%d %H:%M")

    params = {
        "exchange": "NSE",
        "symboltoken": symbol_token,
        "interval": interval,
        "fromdate": start,
        "todate": end
    }

    for _ in range(6):
        try:
            resp = obj.getCandleData(params)
            if resp and resp.get("data"):
                return resp["data"]
        except:
            pass
        time.sleep(1)
    return []


def check_hh_ll(symbol, token, interval):
    data = fetch_last_candles(token, interval)
    if len(data) < 2:
        return (False, False, False, False)

    last21 = data[-21:] if len(data) >= 21 else data
    if len(last21) < 2:
        return (False, False, False, False)

    cur = last21[-1]
    O = float(cur[1])
    H = float(cur[2])
    L = float(cur[3])

    prev = last21[:-1]
    prev20 = prev[-20:] if len(prev) > 20 else prev

    highs = [float(c[2]) for c in prev20]
    lows  = [float(c[3]) for c in prev20]

    maxH = max(highs)
    minL = min(lows)

    exact_hh = H > maxH
    exact_ll = L < minL

    near_hh = not exact_hh and (maxH - H) <= TOL
    near_ll = not exact_ll and (L - minL) <= TOL

    return (exact_hh, exact_ll, near_hh, near_ll)


# HH/LL result containers
HH30 = []; LL30 = []; NH30 = []; NL30 = []
HH1  = []; LL1  = []; NH1  = []; NL1  = []

# RUN HHLL SCAN
for symbol, token in tokens.items():
    eHH, eLL, nHH, nLL = check_hh_ll(symbol, token, "THIRTY_MINUTE")
    if eHH: HH30.append(symbol)
    if eLL: LL30.append(symbol)
    if nHH: NH30.append(symbol)
    if nLL: NL30.append(symbol)

    eHH, eLL, nHH, nLL = check_hh_ll(symbol, token, "ONE_HOUR")
    if eHH: HH1.append(symbol)
    if eLL: LL1.append(symbol)
    if nHH: NH1.append(symbol)
    if nLL: NL1.append(symbol)


# --------------------------------------
# FORMAT TELEGRAM MESSAGE
# --------------------------------------
msg = "*📊 Combined Scanner (OLH + HH/LL)*\n\n"

msg += "*🔥 9:15–9:45 OLH Scanner*\n"
msg += "\n*Exact Open = Low:* " + (", ".join(OL_exact) or "None")
msg += "\n*Exact Open = High:* " + (", ".join(OH_exact) or "None")
msg += "\n*Near OL (≤1):* " + (", ".join(OL_near) or "None")
msg += "\n*Near OH (≤1):* " + (", ".join(OH_near) or "None")

msg += "\n\n*🔥 HH/LL — 30m*\n"
msg += "\n*Exact HH:* " + (", ".join(HH30) or "None")
msg += "\n*Exact LL:* " + (", ".join(LL30) or "None")
msg += "\n*Near HH:* " + (", ".join(NH30) or "None")
msg += "\n*Near LL:* " + (", ".join(NL30) or "None")

msg += "\n\n*🔥 HH/LL — 1H*\n"
msg += "\n*Exact HH:* " + (", ".join(HH1) or "None")
msg += "\n*Exact LL:* " + (", ".join(LL1) or "None")
msg += "\n*Near HH:* " + (", ".join(NH1) or "None")
msg += "\n*Near LL:* " + (", ".join(NL1) or "None")

# SEND TELEGRAM
send_telegram(msg)

print("\n📩 Telegram message sent!\n")
