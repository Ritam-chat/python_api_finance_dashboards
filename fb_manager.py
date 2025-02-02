import os 
from pyairtable import Api


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Use a service account.
cred = credentials.Certificate('SA.json')

app = firebase_admin.initialize_app(cred)

db = firestore.client()


doc_ref = db



def add_to_stash(key,data):
    bank,_ = key.split('_')
    # print(bank)
    doc_ref.collection('Stash').document(bank).set(data)

    return True

def add_record(key, dt, data):

    bank, account = key.split('_')
    # print(bank,account)
    doc_ref.collection(key).document(dt).set(data)

    return True

if __name__ == '__main__':
    ## Show getting certain records
    print("Started")