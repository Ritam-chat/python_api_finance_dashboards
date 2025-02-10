import os
from csv import excel

from pyairtable import Api


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'Cert.json'


# Use a service account.
cred = credentials.Certificate('Cert.json')

app = firebase_admin.initialize_app(cred)

db = firestore.client()


def update_records(records):
    success = True
    db = firestore.client()
    batch = db.batch()
    for key in records:
        bank, acc, k = key.split('~')
        db_ref = db.collection("Ritam").document(bank).collection(acc).document(k)
        batch.set(db_ref,records[key],merge=True)
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

def get_all_records():
    json = {}

    for bank in db.collection('Ritam').list_documents():
        bank_name = bank.get().id
        for acc in bank.collections():
            id = acc.id
            for transaction in acc.stream():
                if transaction.exists:
                    # print(f"\n\nDocument data: {transaction.to_dict()},{transaction}")
                    if bank_name not in json:
                        json[bank_name] = {}
                        json[bank_name][id] = {}
                    if id not in json[bank_name]:
                        json[bank_name][id] = {}
                    json[bank_name][id][transaction.id] = transaction.to_dict()
                else:
                    print("No such document!")
    return json


def add_to_stash(path,data):

    db.document(path).set(data)

    return True

def add_record(path, data):

    db.document(path).set(data)

    return True


if __name__ == '__main__':
    ## Show getting certain records
    print("Started")