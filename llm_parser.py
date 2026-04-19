import os
import re
import json
import logging
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a bank SMS parser for Indian banks. You receive SMS messages that have been pre-scrubbed for privacy — sensitive values like amounts, account numbers, UPI IDs, and reference numbers have been replaced with placeholder tokens like [AMT], [ACCT], [VPA], [REFNO], [DATE], [TIME].

Your job is to analyze the SMS structure and return a single JSON object. No markdown, no explanation, no code fences. Raw JSON only.

First decide: is this a financial transaction SMS? A financial transaction SMS is one that records a debit or credit event — money moving in or out of an account. Non-transaction messages (OTPs, offers, reminders, balance enquiries, service alerts) are NOT transactions.

If it is NOT a transaction, return exactly:
{"is_transaction": false}

If it IS a transaction, return:
{
  "is_transaction": true,
  "type": "Debit" or "Credit",
  "mode": one of ["UPI", "Card", "Withdrawal", "Repayment", "Refund", "Transaction", "Net Banking", "BANK"],
  "accountType": "Savings" or "Credit Card",
  "to_from": "reconstruct a clean payee/payer label using the token position — e.g. if [VPA] appears after 'to', label it 'UPI Payee'; if [ACCT] appears after 'from', label it 'Own Account'; use the structure of the sentence to infer the counterparty role",
  "account": "[ACCT]",
  "amount": "[AMT]",
  "refNo": "[REFNO] or N/A if absent",
  "time": "use readable_date provided",
  "tags": ["auto-assign 1-3 tags from this list based on context clues in the SMS structure: Fuel, Shopping, ATM, Salary, Ignore, Refund, Snacks, SIP, CC Repayment, Food, Travel, Bills, Entertainment, Health, Transfer, UPI"],
  "gps": ""
}

Rules:
- For mode: UPI if [VPA] present; Card if "card" or "pos" in text; Withdrawal if "atm" or "cash" in text; Repayment if "payment" and credit card context; Net Banking if "neft" or "imps" or "rtgs"; BANK for direct bank transfers; Transaction as fallback.
- For accountType: "Credit Card" if "credit card", "cc", "card x[ACCT]" in a spending context; otherwise "Savings".
- For type: "Debit" if money left (spent, debited, withdrawn, transferred); "Credit" if money came in (credited, received, refund, salary).
- The tokens [AMT], [ACCT], [VPA], [REFNO], [DATE], [TIME] are placeholders — keep them exactly as-is in your output. The backend will substitute real values after you respond.
- Do not invent values. If something is unclear, use "N/A" or omit.
"""

def should_skip(address: str, body: str) -> tuple[bool, str]:
    body_lower = body.lower()
    
    known_banks = ["HDFCBK", "SBIINB", "SBISMS", "ONECRD", "IDFCBK", "AXISBK", "ICICIB", "KOTAKB", "PAYTMB", "YESBNK", "BOIIND", "CANBNK", "UNIONB"]
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

    acct_matches = re.finditer(r'(?:x+|X+|ending|a/c|A/cX*)\s*(\d{3,5})(?!\d)', scrubbed, flags=re.IGNORECASE)
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

def parse_with_llm(scrubbed_body: str, address: str, readable_date: str) -> dict | None:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        logger.error("NVIDIA_API_KEY missing - Fallback active")
        # Proceed with empty response for API failure mock, but return None to trigger fallback.
        return None

    try:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
        
        response = client.chat.completions.create(
            model="mistralai/mixtral-8x7b-instruct-v0.1",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"SMS sender: {address}\\nSMS body: {scrubbed_body}\\nDate: {readable_date}"}
            ],
            temperature=0.0,
            max_tokens=400
        )
        
        raw = response.choices[0].message.content.strip()
        
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        
        return json.loads(raw.strip())
        
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
    if 'IDFC' in addr_upper: return 'IDFC'
    if 'AXIS' in addr_upper: return 'AXIS'
    if 'ICICI' in addr_upper: return 'ICICI'
    if 'KOTAK' in addr_upper: return 'KOTAK'
    if 'PAYTM' in addr_upper: return 'PAYTM'
    if 'YESB' in addr_upper: return 'YESB'
    if 'BOI' in addr_upper: return 'BOI'
    if 'CANBNK' in addr_upper: return 'CANARA'
    if 'UNION' in addr_upper: return 'UNION'
    return 'Unknown'
