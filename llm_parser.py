import os
import re
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert bank SMS parser specializing in Indian banking notifications. Your goal is to convert semi-structured bank SMS text into a precise JSON format.

### INPUT FORMAT
You will receive:
1. SMS Sender (Address)
2. Raw SMS Body
3. A reference date/time (the approximate time the SMS arrived)

### CLASSIFICATION RULE
First, determine if the message represents a **financial transaction**.
- **Financial Transaction**: Money is either deducted from (Debit) or added to (Credit) the user's account.
- **Non-Transaction**: OTPs, balance inquiries, limit alerts, statement notifications, or promotional offers. If non-transactional, return exactly: `{"is_transaction": false}`.

### JSON SCHEMA DEFINITION
If it is a transaction, return a raw JSON object with these EXACT attributes:

1. **"is_transaction"** (Boolean): Must be `true`.
2. **"type"** (String): 
   - "Debit": If money left the account (Spent, Sent, Debited, Withdrawn, Paid).
   - "Credit": If money entered the account (Received, Credited, Refund, Salary).
3. **"mode"** (String): The channel used. Choose one:
   - "UPI": If the text contains VPA, UPI, GPay, PhonePe, or similar.
   - "Card": If card, swipe, online, purchase, or a card number is indicated.
   - "Withdrawal": If ATM, cash, or withdrawn at ATM.
   - "Repayment": If the user is paying a Credit Card bill or Loan EMI.
   - "Transfer": If it's a direct bank transfer (IMPS, NEFT, RTGS).
   - "Transaction": Fallback for general services.
4. **"accountType"** (String):
   - "Credit Card": If keywords like "Card no.", "Limit", "Available Limit" appear in a spending context.
   - "Savings": Default for standard bank A/C or Wallet notifications.
5. **"account"** (String): Extract the last 4 digits of the account number or card number mentioned (e.g., from "A/C *5808" extract "5808", from "XX2981" extract "2981"). 
   - **IMPORTANT**: If the input 'USER'S CONFIGURED ACCOUNTS' contains an account with a 'linkedCards' map, and the SMS mentions one of those card numbers, return the 'accountDigits' of that account as the "account" value.
   - Also, if a linked card matches, add "Debit Card Transaction" and the card's nickname (from the map) to the **"tags"** array.
6. **"to_from"** (String): The counterparty name.
   - For Debits: The merchant name (e.g., "HungerBox", "Amazon") or person name.
   - For Credits: The source of funds.
   - Clean the name: Remove filler words like "at", "to", "info", "on".
7. **"amount"** (String): The **numerical transaction amount** (e.g. "104.74"). 
   - IMPORTANT: Do NOT confuse the transaction amount with the "Available Balance" or "Limit" which may also be present in the text.
8. **"refNo"** (String): Extract the reference number, transaction ID, or UTR number if present. Otherwise "N/A".
9. **"time"** (String): Use the provided reference date/time as the value.
10. **"category"** (String): High-level category. Pick the single best match from: [Food & Dining, Shopping, Transportation, Travel, Bills & Utilities, Entertainment, Health & Wellness, Investments, Income, Transfers, Miscellaneous].
11. **"tags"** (Array of Strings): 1-3 relevant labels. 
    - If "Provided Tags" is given in the input, merge or prioritize them.
    - Otherwise, use labels from this set: [Food, Shopping, Travel, Bills, Entertainment, Health, SIP, CC Repayment, Fuel, Salary, ATM, Ignore, Refund, Transfer, UPI].
12. **"gps"** (String): If "Provided GPS Coordinates" is given in the input, return it as is in the Json. Otherwise, return `""`.

### STRICT RULES
- No markdown code fences.
- No conversational text.
- No invented values.
- Return raw JSON only.
"""

def should_skip(address: str, body: str) -> tuple[bool, str]:
    body_lower = body.lower()
    known_banks = ["HDFCBK", "SBIUPI", "CBSSBI", "SBIINB", "SBISMS", "ONECRD", "FEDONE", "IDFCBK", "AXISBK", "ICICIB", "KOTAKB", "PAYTMB", "YESBNK", "BOIIND", "CANBNK", "UNIONB"]
    if not any(bank in address.upper() for bank in known_banks):
        return True, f"Address '{address}' not in known bank whitelist"

    if len(body) < 30:
        return True, "Body less than 30 characters"

    otp_patterns = ["otp", "one time password", "verification code", "use code", "do not share", "is your", "expires in", "valid for"]
    if any(pat in body_lower for pat in otp_patterns):
        return True, "Contains OTP indicator"

    promo_patterns = ["offer", "cashback", "win", "congratulations", "discount", "% off", "click here", "unsubscribe", "reply stop", "deal", "limited time", "exclusive", "upgrade your plan"]
    if any(pat in body_lower for pat in promo_patterns):
        return True, "Contains promotional indicator"

    alert_patterns = ["due date", "minimum due", "payment due", "statement generated", "your bill", "auto-debit", "standing instruction"]
    if any(pat in body_lower for pat in alert_patterns):
        return True, "Contains non-transaction alert indicator"

    currency_patterns = ["rs.", "inr", "rs", "₹", "debited", "credited", "spent", "transferred", "withdrawn", "received"]
    if not any(pat in body_lower for pat in currency_patterns):
        return True, "No currency/transaction indicator"

    return False, ""


def scrub_sms(body: str) -> tuple[str, dict]:
    tokens = {}
    scrubbed = body

    vpa_matches = re.finditer(r'[a-zA-Z0-9.\-_]+@[a-zA-Z]+', scrubbed)
    for m in vpa_matches:
        vpa = m.group(0)
        tokens['[VPA]'] = vpa
        scrubbed = scrubbed.replace(vpa, '[VPA]')

    amt_matches = re.finditer(r'(?:Rs\.?|INR|₹|rs\.?)\s*([\d,]+(?:\.\d+)?)(?![a-zA-Z@])', scrubbed, flags=re.IGNORECASE)
    for m in amt_matches:
        amt_raw = m.group(1).replace(',', '')
        tokens['[AMT]'] = amt_raw
        scrubbed = scrubbed.replace(m.group(0), "Rs.[AMT]")

    acct_matches = re.finditer(r'(?:x+|X+|ending|a/c|A/cX*|acct|account).{0,10}?(\d{3,5})(?!\d)', scrubbed, flags=re.IGNORECASE)
    for m in acct_matches:
        acct = m.group(1)
        tokens['[ACCT]'] = acct
        scrubbed = scrubbed.replace(acct, '[ACCT]')

    phone_matches = re.finditer(r'(?:\+91|91)?\s*[6-9]\d{9}', scrubbed)
    for m in phone_matches:
        phone = m.group(0)
        if phone not in tokens.values():
            tokens['[PHONE]'] = phone
            scrubbed = scrubbed.replace(phone, '[PHONE]')

    ref_matches = re.finditer(r'\b\d{12,}\b', scrubbed)
    for m in ref_matches:
        ref = m.group(0)
        if ref not in tokens.values():
            tokens['[REFNO]'] = ref
            scrubbed = scrubbed.replace(ref, '[REFNO]')

    date_matches = re.finditer(r'\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', scrubbed)
    for m in date_matches:
        dt = m.group(0)
        tokens['[DATE]'] = dt
        scrubbed = scrubbed.replace(dt, '[DATE]')

    time_matches = re.finditer(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\b', scrubbed)
    for m in time_matches:
        tm = m.group(0)
        tokens['[TIME]'] = tm
        scrubbed = scrubbed.replace(tm, '[TIME]')

    return scrubbed, tokens

def parse_with_llm(body: str, address: str, readable_date: str, configured_banks: list = None, request_tags: list = None, request_gps: str = "", custom_tags: list = None, categories: list = None, categorization_rules: dict = None) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY missing - Fallback active")
        return None

    try:
        client = OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=api_key
        )
        
        user_prompt = f"SMS sender: {address}\nSMS body: {body}\nReference Date/Time: {readable_date}"
        
        if request_tags:
            user_prompt += f"\nProvided Tags: {json.dumps(request_tags)}"
        if request_gps:
            user_prompt += f"\nProvided GPS Coordinates: {request_gps}"

        if configured_banks:
            user_prompt += f"\n\n### USER'S CONFIGURED ACCOUNTS (Ground Truth)\n{json.dumps(configured_banks, indent=2)}\n"
            user_prompt += "\nUse the above JSON to cross-verify the bank and account suffix."

        # Dynamically inject custom tags or use default
        effective_tags_list = custom_tags if custom_tags and len(custom_tags) > 0 else ["Food", "Shopping", "Travel", "Bills", "Entertainment", "Health", "SIP", "CC Repayment", "Fuel", "Salary", "ATM", "Ignore", "Refund", "Transfer", "UPI"]
        effective_categories = categories if categories and len(categories) > 0 else ["Food & Dining", "Shopping", "Transportation", "Travel", "Bills & Utilities", "Entertainment", "Health & Wellness", "Investments", "Income", "Transfers", "Miscellaneous"]

        dynamic_system_prompt = SYSTEM_PROMPT.replace(
            "[Food, Shopping, Travel, Bills, Entertainment, Health, SIP, CC Repayment, Fuel, Salary, ATM, Ignore, Refund, Transfer, UPI]",
            f"[{', '.join(effective_tags_list)}]"
        ).replace(
            "[Food & Dining, Shopping, Transportation, Travel, Bills & Utilities, Entertainment, Health & Wellness, Investments, Income, Transfers, Miscellaneous]",
            f"[{', '.join(effective_categories)}]"
        )

        response = client.chat.completions.create(
            # model="gemini-2.5-flash",
            model="gemini-3-flash-preview",
            messages=[
                {"role": "system", "content": dynamic_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        raw = response.choices[0].message.content.strip()
        
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        
        parsed = json.loads(raw.strip())

        # Apply deterministic user rules if to_from matches
        if isinstance(parsed, dict) and categorization_rules and parsed.get('to_from'):
            merchant_lower = parsed['to_from'].lower()
            for pattern, rule_cat in categorization_rules.items():
                if pattern and pattern.lower().strip() in merchant_lower:
                    parsed['category'] = rule_cat
                    break

        return parsed
        
    except Exception as e:
        logger.error(f"LLM Parse Error: {e}")
        return None

def reconstruct(llm_json: dict, tokens: dict) -> dict:
    if isinstance(llm_json, dict):
        return {k: reconstruct(v, tokens) for k, v in llm_json.items()}
    elif isinstance(llm_json, list):
        return [reconstruct(i, tokens) for i in llm_json]
    elif isinstance(llm_json, str):
        res = llm_json
        for tk, val in tokens.items():
            res = res.replace(tk, val)
        return res
    else:
        return llm_json

def detect_bank(address: str) -> str:
    addr_upper = address.upper()
    if 'HDFC' in addr_upper: return 'HDFC'
    if 'SBI' in addr_upper: return 'SBI'
    if 'ONECRD' in addr_upper: return 'ONE'
    if 'FEDONE' in addr_upper: return 'ONE'
    if 'IDFC' in addr_upper: return 'IDFC'
    if 'AXIS' in addr_upper: return 'AXIS'
    if 'ICICI' in addr_upper: return 'ICICI'
    if 'KOTAK' in addr_upper: return 'KOTAK'
    if 'PAYTM' in addr_upper: return 'PAYTM'
    if 'YESB' in addr_upper: return 'YES BANK'
    if 'KIWI' in addr_upper: return 'KIWI'
    if 'HSBC' in addr_upper: return 'HSBC'
    if 'BOI' in addr_upper: return 'BOI'
    if 'CANBNK' in addr_upper: return 'CANARA'
    if 'UNION' in addr_upper: return 'UNION'
    return 'Unknown'
