import os
import time
from csv import excel
import concurrent.futures

from pyairtable import Api


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

cert_candidates = [
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    os.path.join(BASE_DIR, 'app_data', 'Cert.json'),
    os.path.join(BASE_DIR, 'app_data', 'cert.json'),
    os.path.join(BASE_DIR, 'SA.json'),
]

db = None

def get_db():
    global db
    if db is not None:
        return db

    for p in cert_candidates:
        if p and os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = p
                cred = credentials.Certificate(p)
                try:
                    firebase_admin.get_app()
                except ValueError:
                    firebase_admin.initialize_app(cred)
                db = firestore.client()
                return db
            except Exception as e:
                print(f"[ERROR] Failed to initialize Firebase with {p}: {e}")
                return None

    print(f"[WARNING] Firebase credentials not found or empty in {BASE_DIR}/app_data/Cert.json or SA.json.")
    return None

# Try initializing on startup
get_db()


def update_records(user, records):
    current_db = get_db()
    if current_db is None:
        print("[ERROR] Firebase database not initialized. Cannot update records.")
        return False

    success = True
    batch = current_db.batch()
    for key in records:
        bank, acc, k = key.split('~')
        db_ref = current_db.collection(user).document(bank).collection(acc).document(k)
        batch.set(db_ref,records[key],merge=True)
    try:
        batch.commit()
        success = True
        invalidate_records_cache()
    except Exception as e:
        success = False
        print(f"\n\nError : {e}")

    return success


def import_all_from_xml(records,stash):
    current_db = get_db()
    if current_db is None:
        print("[ERROR] Firebase database not initialized. Cannot import.")
        return False

    success = True
    record_batch = current_db.batch()
    stash_batch = current_db.batch()
    for item in records:
        path = item[0]
        json = item[1]
        record_ref = current_db.document(path)
        record_batch.set(record_ref,json)

    for item in stash:
        path = item[0]
        json = item[1]
        stash_ref = current_db.document(path)
        stash_batch.set(stash_ref,json)

    try:
        record_batch.commit()
        rec_success = True
    except Exception as e:
        rec_success = False
        print(f"\n\nRec Error : {e}")

    try:
        stash_batch.commit()
        sts_success = True
    except Exception as e:
        sts_success = False
        print(f"\n\nsts Error : {e}")

    return sts_success and rec_success

EXCLUDE_BANKS = {'Memo', 'Settings', 'userInfo', 'Stash'}

_RECORDS_CACHE = {}
_CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 minutes cache to prevent hitting Firestore daily read quota

def invalidate_records_cache():
    global _CACHE_TIMESTAMP
    _CACHE_TIMESTAMP = 0

def get_all_records(user='Ritam', since=None):
    global _RECORDS_CACHE, _CACHE_TIMESTAMP

    # Return cached data if fresh
    if _RECORDS_CACHE and (time.time() - _CACHE_TIMESTAMP < CACHE_TTL):
        return _RECORDS_CACHE

    current_db = get_db()
    if current_db is None:
        print(f"[ERROR] Firebase database not initialized. Please copy your Firebase service account key to {BASE_DIR}/app_data/Cert.json")
        return _RECORDS_CACHE or {}

    # Quick probe with 2.0s deadline to fail fast if Firestore quota is exceeded
    try:
        from google.api_core.retry import Retry
        current_db.collection(user).document('AXIS').get(retry=Retry(maximum=1.0, deadline=2.0), timeout=2.0)
    except Exception as e:
        if 'Quota' in str(e) or 'ResourceExhausted' in str(e) or '429' in str(e):
            print(f"[WARNING] Firestore read quota exceeded on Firebase project: {e}")
            return _RECORDS_CACHE or {}

    json_data = {}

    def fetch_collection(bank_name, coll_ref):
        coll_id = coll_ref.id
        docs = {}
        for transaction in coll_ref.stream():
            if transaction.exists:
                docs[transaction.id] = transaction.to_dict()
        return bank_name, coll_id, docs

    try:
        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for bank in current_db.collection(user).list_documents():
                bank_name = bank.id
                if bank_name in EXCLUDE_BANKS:
                    continue
                for acc in bank.collections():
                    tasks.append(executor.submit(fetch_collection, bank_name, acc))

            for future in concurrent.futures.as_completed(tasks):
                try:
                    bname, acc_id, docs = future.result()
                    if bname not in json_data:
                        json_data[bname] = {}
                    json_data[bname][acc_id] = docs
                except Exception as e:
                    print(f"[ERROR] Failed fetching subcollection: {e}")

        if json_data:
            _RECORDS_CACHE = json_data
            _CACHE_TIMESTAMP = time.time()
        return json_data or _RECORDS_CACHE or {}
    except Exception as e:
        print(f"[ERROR] Firestore error in get_all_records: {e}")
        return _RECORDS_CACHE or {}


def add_to_stash(path,data):
    current_db = get_db()
    if current_db is None:
        print("[ERROR] Firebase database not initialized.")
        return False

    current_db.document(path).set(data)
    return True

def add_record(path, data):
    current_db = get_db()
    if current_db is None:
        print("[ERROR] Firebase database not initialized.")
        return False

    current_db.document(path).set(data)
    invalidate_records_cache()
    return True


def get_settings(user='Ritam'):
    current_db = get_db()
    if current_db is None:
        return {}

    doc_ref = current_db.collection(user).document('Settings')
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {}

def update_settings(user, data):
    current_db = get_db()
    if current_db is None:
        return False

    doc_ref = current_db.collection(user).document('Settings')
    try:
        doc_ref.set(data, merge=True)
        return True
    except Exception as e:
        print(f"Settings Error: {e}")
        return False


if __name__ == '__main__':
    ## Show getting certain records
    print("Started")