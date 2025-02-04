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
        batch.update(db_ref,records[key])
    try:
        batch.commit()
        success = True
    except Exception as e:
        success = False
        print(f"\n\nError : {e}")

    return success

def get_all_records():
    json = {}

    for bank in db.collection('Ritam').list_documents():
        bank_name = bank.get().id
        for acc in bank.collections():
            for trans in acc.list_documents():
                transaction = trans.get()
                if transaction.exists:
                    # print(f"\n\nDocument data: {transaction.to_dict()},{transaction}")

                    if bank_name not in json:
                        json[bank_name] = {}
                        json[bank_name][acc.id] = {}
                    if acc.id not in json[bank_name]:
                        json[bank_name][acc.id] = {}
                    json[bank_name][acc.id][transaction.id] = transaction.to_dict()
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