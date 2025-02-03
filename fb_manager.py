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



def add_to_stash(path,data):

    doc_ref.document(path).set(data)

    return True

def add_record(path, data):

    doc_ref.document(path).set(data)

    return True

if __name__ == '__main__':
    ## Show getting certain records
    print("Started")