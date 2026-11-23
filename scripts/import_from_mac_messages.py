#!/usr/bin/env python3
"""
Import Missing Bank SMS from Mac Messages (chat.db)
For Finance Tracker (15 Nov 2026 to 23 Nov 2026)

This script:
1. Reads SMS from ~/Library/Messages/chat.db (or /tmp/chat.db) for the given date range.
2. Decodes message text (handling both plain text and modern macOS attributedBody).
3. Filters for bank messages (matching known banks and configured bank sender patterns).
4. Sends them to the Finance Tracker API (/add-record) or tests with --dry-run.

Usage:
  # Dry-run preview (does not save anything to DB):
  python3 scripts/import_from_mac_messages.py --dry-run

  # Import to local dev server (default port 5001):
  python3 scripts/import_from_mac_messages.py --local

  # Import directly to production (Vercel):
  python3 scripts/import_from_mac_messages.py --prod

  # Custom date range:
  python3 scripts/import_from_mac_messages.py --from-date 2026-11-15 --to-date 2026-11-23
"""

import os
import sys
import sqlite3
import argparse
import json
import re
import time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

# Ensure Backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Apple Cocoa Epoch starts at 2001-01-01 00:00:00 UTC
APPLE_EPOCH_OFFSET = 978307200

# Common Indian Bank SMS Sender Keywords & Prefixes
KNOWN_BANK_HINTS = [
    "HDFC", "KOTAK", "HSBC", "ICICI", "AXIS", "SBI", "IDFC", "RBL", "AMEX",
    "INDUS", "PNB", "BOB", "CANARA", "UNION", "YES", "CITI", "SCB", "FEDERAL",
    "JUPITER", "FI", "ONE", "SLICE", "CRED", "PAYTM", "BHIM", "UPI"
]

def decode_attributed_body(data: bytes) -> str:
    """Extract plain text from macOS NSAttributedString typedstream/plist binary blob."""
    if not data:
        return ""
    try:
        if b"NSString" in data:
            pos = data.find(b"NSString")
            slice_data = data[pos + 8:]
            for i in range(len(slice_data)):
                # Printable ASCII range
                if 32 <= slice_data[i] <= 126:
                    chunk = slice_data[i:]
                    end_idx = 0
                    while end_idx < len(chunk) and (chunk[end_idx] >= 32 or chunk[end_idx] in (10, 13)):
                        end_idx += 1
                    if end_idx > 6:
                        return chunk[:end_idx].decode("utf-8", errors="ignore").strip()
    except Exception:
        pass

    # Regex fallback for printable sequences
    matches = re.findall(rb'[\x20-\x7E\n\r]{8,}', data)
    for m in matches:
        if not any(token in m for token in (b'NSString', b'NSDictionary', b'NSFont', b'NSColor', b'NSNumber')):
            decoded = m.decode("utf-8", errors="ignore").strip()
            if any(w in decoded.lower() for w in ['debited', 'credited', 'spent', 'rs', 'inr', 'a/c', 'card', 'bank']):
                return decoded
    return ""

def locate_chat_db() -> str:
    """Finds chat.db, checking /tmp copy first then ~/Library/Messages/chat.db."""
    tmp_path = "/tmp/chat.db"
    if os.path.exists(tmp_path):
        return tmp_path

    primary_path = os.path.expanduser("~/Library/Messages/chat.db")
    if os.path.exists(primary_path):
        return primary_path

    return primary_path

def convert_apple_date_to_datetime(apple_date: int) -> datetime:
    """Converts Apple Cocoa timestamp (nanoseconds or seconds) to UTC datetime."""
    if apple_date > 10**15:
        # Nanoseconds
        sec = (apple_date / 1_000_000_000) + APPLE_EPOCH_OFFSET
    elif apple_date > 10**11:
        # Microseconds
        sec = (apple_date / 1_000_000) + APPLE_EPOCH_OFFSET
    else:
        # Seconds
        sec = apple_date + APPLE_EPOCH_OFFSET
    return datetime.fromtimestamp(sec, tz=timezone.utc)

def fetch_messages_from_db(db_path: str, start_dt: datetime, end_dt: datetime):
    """Queries messages from SQLite within the date range."""
    # Convert start_dt and end_dt to Apple nanoseconds
    start_sec = start_dt.timestamp() - APPLE_EPOCH_OFFSET
    end_sec = end_dt.timestamp() - APPLE_EPOCH_OFFSET
    start_nano = int(start_sec * 1_000_000_000)
    end_nano = int(end_sec * 1_000_000_000)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT 
        m.ROWID as id,
        m.date,
        m.text,
        m.attributedBody,
        COALESCE(h.id, c.chat_identifier, '') AS sender,
        m.is_from_me
    FROM message m
    LEFT JOIN handle h ON m.handle_id = h.ROWID
    LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
    LEFT JOIN chat c ON cmj.chat_id = c.ROWID
    WHERE m.is_from_me = 0
      AND m.date >= ? AND m.date <= ?
    ORDER BY m.date ASC
    """
    
    cursor.execute(query, (start_nano, end_nano))
    rows = cursor.fetchall()
    messages = []

    for r in rows:
        sender = r["sender"] or ""
        text = r["text"]
        if not text and r["attributedBody"]:
            text = decode_attributed_body(r["attributedBody"])
        
        if not text:
            continue

        msg_dt = convert_apple_date_to_datetime(r["date"])
        # Convert to local IST (+5:30) for display & readable_date
        ist_offset = timedelta(hours=5, minutes=30)
        local_dt = msg_dt.astimezone(timezone(ist_offset))

        messages.append({
            "id": r["id"],
            "date": local_dt,
            "sender": sender.strip(),
            "body": text.strip(),
            "readable_date": local_dt.strftime("%d/%m/%y %I:%M %p")
        })

    conn.close()
    return messages

def is_probable_bank_sms(sender: str, body: str) -> bool:
    """Quick check to filter non-financial spam or family texts."""
    sender_upper = sender.upper()
    body_lower = body.lower()

    # Financial keywords
    has_keywords = any(kw in body_lower for kw in [
        "debited", "credited", "spent", "spent on", "txn", "transaction",
        "inr", "rs.", "rs ", "a/c", "acct", "card ending", "vpa", "upi"
    ])

    # Bank sender indicators (e.g. AX-HDFCBK, VK-KOTAKB, VM-HSBCIN, 6-digit sender code)
    has_bank_sender = any(b in sender_upper for b in KNOWN_BANK_HINTS) or ("-" in sender_upper and len(sender_upper) <= 12)

    return has_keywords and has_bank_sender

def post_record(api_url: str, user: str, sender: str, body: str, readable_date: str) -> tuple[bool, str]:
    """Posts record to /add-record API."""
    payload = {
        "address": sender,
        "body": body,
        "readable_date": readable_date
    }
    req = urllib.request.Request(
        f"{api_url}/add-record",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "user": user,
            "Username": user
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body) if resp_body else {}
            msg = data.get("message", "OK")
            return (resp.status == 200, msg)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        return (False, f"HTTP {e.code}: {err_msg}")
    except Exception as e:
        return (False, str(e))

def main():
    parser = argparse.ArgumentParser(description="Import missing bank SMS from Mac Messages (chat.db)")
    parser.add_argument("--from-date", default="2026-11-15", help="Start date (YYYY-MM-DD), default 2026-11-15")
    parser.add_argument("--to-date", default="2026-11-23", help="End date (YYYY-MM-DD), default 2026-11-23")
    parser.add_argument("--user", default="Ritam", help="Username for database, default 'Ritam'")
    parser.add_argument("--local", action="store_true", help="Post to local server (http://127.0.0.1:5001)")
    parser.add_argument("--prod", action="store_true", help="Post to production (https://finance---api.vercel.app)")
    parser.add_argument("--dry-run", action="store_true", help="Only scan & print detected messages, don't post")
    parser.add_argument("--db-path", default=None, help="Custom path to chat.db if copied elsewhere")
    args = parser.parse_args()

    # Determine API target URL
    if args.prod:
        api_url = "https://finance---api.vercel.app"
    else:
        api_url = "http://127.0.0.1:5001"

    print("=" * 65)
    print(" 💳 Finance Tracker: Mac Messages Missing SMS Importer")
    print("=" * 65)

    # Date range in UTC
    try:
        # Start at 00:00:00 IST of from-date
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        from_dt = datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=ist_offset).astimezone(timezone.utc)
        to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=ist_offset).astimezone(timezone.utc)
    except ValueError as e:
        print(f"❌ Invalid date format: {e}. Please use YYYY-MM-DD.")
        sys.exit(1)

    print(f"📅 Scanning date range: {args.from_date} to {args.to_date} (IST)")
    print(f"👤 Target User: {args.user}")
    print(f"🌐 Target API:  {api_url} {'(DRY RUN ONLY)' if args.dry_run else ''}")

    db_path = args.db_path or locate_chat_db()
    print(f"📂 Messages DB:  {db_path}")

    if not os.path.exists(db_path):
        print(f"\n❌ Error: Cannot find chat.db at '{db_path}'")
        sys.exit(1)

    # Query DB
    try:
        messages = fetch_messages_from_db(db_path, from_dt, to_dt)
    except (sqlite3.Error, Exception) as e:
        err_str = str(e).lower()
        if "authorization denied" in err_str or "unable to open database" in err_str or "permission denied" in err_str:
            print("\n" + "!" * 65)
            print("🔒 macOS Full Disk Access Required")
            print("!" * 65)
            print("macOS protects ~/Library/Messages/chat.db with privacy security.")
            print("\n👉 Quick 10-second fix: Copy chat.db to /tmp:")
            print("   Run this command in your Terminal:")
            print("   cp ~/Library/Messages/chat.db /tmp/chat.db && cp ~/Library/Messages/chat.db-wal /tmp/chat.db-wal 2>/dev/null || true")
            print("   Then re-run this script!\n")
            print("👉 Alternative: Grant Full Disk Access:")
            print("   System Settings -> Privacy & Security -> Full Disk Access -> enable Terminal/iTerm.")
            print("!" * 65)
            sys.exit(1)
        else:
            print(f"\n❌ Database error: {e}")
            sys.exit(1)

    print(f"📥 Found {len(messages)} total incoming messages in date range.")

    bank_messages = [m for m in messages if is_probable_bank_sms(m["sender"], m["body"])]
    print(f"🏦 Filtered {len(bank_messages)} probable bank/transaction messages.\n")

    if not bank_messages:
        print("ℹ️ No bank messages found in this date range.")
        return

    # Print summary table
    print("-" * 65)
    for idx, msg in enumerate(bank_messages, 1):
        clean_preview = msg["body"].replace("\n", " ")[:60]
        print(f"[{idx:2d}] {msg['readable_date']} | {msg['sender']:<12} | {clean_preview}...")
    print("-" * 65)

    if args.dry_run:
        print(f"\n✅ Dry run completed! {len(bank_messages)} messages would be sent to {api_url}/add-record.")
        print("To import them for real, run with --local or --prod without --dry-run.")
        return

    # Process and Post Records
    print(f"\n🚀 Sending {len(bank_messages)} records to {api_url}/add-record...")
    success_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, msg in enumerate(bank_messages, 1):
        print(f"[{idx}/{len(bank_messages)}] Sending SMS from {msg['sender']} ({msg['readable_date']})...", end=" ")
        ok, res_msg = post_record(api_url, args.user, msg["sender"], msg["body"], msg["readable_date"])
        if ok:
            if "Skipped:" in res_msg or "needs_review" in res_msg:
                skipped_count += 1
                print(f"⏭️  {res_msg}")
            else:
                success_count += 1
                print(f"✅ {res_msg}")
        else:
            failed_count += 1
            print(f"❌ Failed: {res_msg}")
        # Brief pause to avoid rate limits
        time.sleep(0.5)

    print("\n" + "=" * 65)
    print(f"🎉 Import Summary:")
    print(f"   Total Processed: {len(bank_messages)}")
    print(f"   ✅ Saved:        {success_count}")
    print(f"   ⏭️  Skipped:      {skipped_count}")
    print(f"   ❌ Failed:       {failed_count}")
    print("=" * 65)

if __name__ == "__main__":
    main()
