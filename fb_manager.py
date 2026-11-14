import os
from csv import excel
import concurrent.futures
import time

from pyairtable import Api


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = '/app_data/Cert.json'


# Use a service account.
cred = credentials.Certificate('./app_data/Cert.json')

app = firebase_admin.initialize_app(cred)

db = firestore.client()


def update_records(user, records):
    import time
    success = True
    db = firestore.client()
    batch = db.batch()
    for key in records:
        bank, acc, k = key.split('~')
        db_ref = db.collection(user).document(bank).collection(acc).document(k)
        rec = records[key]
        rec['updatedAt'] = int(time.time() * 1000)
        batch.set(db_ref, rec, merge=True)
    try:
        batch.commit()
        success = True
    except Exception as e:
        success = False
        print(f"\n\nError : {e}")

    return success


def import_all_from_xml(records,stash):
    success = True

    db = firestore.client()
    record_batch = db.batch()
    stash_batch = db.batch()
    for item in records:
        path = item[0]
        json = item[1]
        record_ref = db.document(path)
        record_batch.set(record_ref,json)

    for item in stash:
        path = item[0]
        json = item[1]
        stash_ref = db.document(path)
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

def get_all_records(user='Ritam', since_timestamp=None):
    res_json = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        # Step 1: List all bank documents (discovery)
        try:
            bank_refs = list(db.collection(user).list_documents())
        except Exception as e:
            print(f"Error listing banks: {e}")
            return {}

        # Step 2: List collections for all banks in parallel
        def get_colls(b_ref):
            try:
                return b_ref.id, list(b_ref.collections())
            except:
                return b_ref.id, []

        bank_coll_futures = [executor.submit(get_colls, b) for b in bank_refs]
        
        # Step 3: Identify all query tasks
        stream_tasks = []
        for future in concurrent.futures.as_completed(bank_coll_futures):
            b_id, collections = future.result()
            for coll in collections:
                stream_tasks.append((b_id, coll))
                
        # Step 4: Stream transactions in parallel
        def fetch_stream(b_id, acc):
            acc_id = acc.id
            query = acc
            if since_timestamp and int(since_timestamp) > 0:
                query = acc.where('updatedAt', '>', int(since_timestamp))
            
            data = {}
            try:
                for doc in query.stream():
                    if doc.exists:
                        data[doc.id] = doc.to_dict()
            except Exception as e:
                print(f"Error streaming {b_id}/{acc_id}: {e}")
            return b_id, acc_id, data

        final_futures = [executor.submit(fetch_stream, tid, tcoll) for tid, tcoll in stream_tasks]
        
        for future in concurrent.futures.as_completed(final_futures):
            b_id, a_id, txs = future.result()
            if txs:
                if b_id not in res_json: res_json[b_id] = {}
                res_json[b_id][a_id] = txs
                
    return res_json

def add_record(path, data):
    import time
    if 'updatedAt' not in data:
        data['updatedAt'] = int(time.time() * 1000)
    db.document(path).set(data)
    return True


def add_to_stash(path, data):
    import time
    if 'updatedAt' not in data:
        data['updatedAt'] = int(time.time() * 1000)
    db.document(path).set(data)
    return True

def get_stash(user='Ritam', since_timestamp=None):
    json_list = []
    # Path: /{user}/Stash/{address}/{time_id}
    # doc(user, 'Stash') is a document that contains subcollections (addresses)
    stash_doc_ref = db.collection(user).document('Stash')
    
    # Iterate through all sub-collections (which are addresses)
    for address_col in stash_doc_ref.collections():
        address = address_col.id
        
        query = address_col
        if since_timestamp and int(since_timestamp) > 0:
            query = address_col.where('updatedAt', '>', int(since_timestamp))
            
        # Stream all documents in this address collection
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            data['address'] = address
            json_list.append(data)
            
    # Sort by updatedAt or ID descending
    return sorted(json_list, key=lambda x: x.get('updatedAt', 0), reverse=True)

def delete_stash_item(user, address, time_id):
    try:
        db.collection(user).document('Stash').collection(address).document(time_id).delete()
        return True
    except Exception as e:
        print(f"Delete Stash Error: {e}")
        return False

def clear_stash(user):
    try:
        stash_doc_ref = db.collection(user).document('Stash')
        # Iterate over all sub-collections
        for address_col in stash_doc_ref.collections():
            # Delete all documents in this subcollection
            for doc in address_col.stream():
                doc.reference.delete()
        return True
    except Exception as e:
        print(f"Clear Stash Error: {e}")
        return False

def add_record(path, data):
    import time
    data['updatedAt'] = int(time.time() * 1000)
    # Strip any potential trailing slashes which cause Firestore InvalidArgument errors
    clean_path = path.strip('/')
    db.document(clean_path).set(data)
    return True


def get_settings(user='Ritam'):
    doc_ref = db.collection(user).document('Settings')
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {}

def update_settings(user, data):
    doc_ref = db.collection(user).document('Settings')
    try:
        doc_ref.set(data, merge=True)
        return True
    except Exception as e:
        print(f"Settings Error: {e}")
        return False


def encrypt(message, key):
    key = int(''.join(str(ord(c)) for c in key))
    encrypted = ""
    for char in message:
        if char.isalpha():
            if char.islower():
                encrypted += chr((ord(char) - ord('a') + key) % 26 + ord('a'))
            else:
                encrypted += chr((ord(char) - ord('A') + key) % 26 + ord('A'))
        else:
            encrypted += char
    return encrypted

def decrypt(encrypted_message, key):
    key = int(''.join(str(ord(c)) for c in key))
    decrypted = ""
    for char in encrypted_message:
        if char.isalpha():
            if char.islower():
                decrypted += chr((ord(char) - ord('a') - key) % 26 + ord('a'))
            else:
                decrypted += chr((ord(char) - ord('A') - key) % 26 + ord('A'))
        else:
            decrypted += char
    return decrypted

def verify_creds(username, password):
    db = firestore.client()
    info = db.collection(username).document('userInfo').get()
    if info.exists and decrypt(info.to_dict().get('password', ''), username) == password:
        return True
    return False

def add_new_user(data):
    try:
        db = firestore.client()
        user = data['username']
        data['password'] = encrypt(data['password'],user)
        if not db.document(f"{user}/userInfo").get().exists:
            db.document(f"{user}/userInfo").set(data)
        else:
            return False, 404
        return True, 500
    except Exception as e:
        print(e.__str__())
        return False, ''

def get_users():
    db = firestore.client()
    users = []
    for docs in db.collections():
        name = docs.id
        doc = db.collection(name).document('userInfo').get()
        if doc.exists and doc.to_dict().get('verified'):
            users.append(name)
    return users

def update_memo(user, memo):
    db = firestore.client()
    batch = db.batch()
    db_ref = db.collection(user).document('Memo')
    batch.set(db_ref, memo, merge=True)
    try:
        batch.commit()
        success = True
    except Exception as e:
        success = False
        print(f"\n\nError : {e}")
    return success

if __name__ == '__main__':
    print("Started")