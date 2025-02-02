import os 
from pyairtable import Api


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'Cert.json'


# Use a service account.
cred = credentials.Certificate('Cert.json')

app = firebase_admin.initialize_app(cred)

db = firestore.client()


doc_ref = db

print()
# doc = doc_ref.collection('HDFC_6484').document('12-Jan-2023 9:18:35 am').get()
# if doc.exists:
#     print(f"Document data: {doc.to_dict()}")
# else:
#     print("No such document!")


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