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



def get_all_records(count=None, sort=None):
    sort_param = []
    if sort and sort.upper()=='DESC':
        sort_param = ['-Rating']
    elif sort and sort.upper()=='ASC':
        sort_param = ['Rating']

    return table.all(max_records=count, sort=sort_param)

def get_record_id(name):
    return doc_ref.get(name)
    return table.first(formula=f"Book='{name}'")['id']

def update_record(record_id, data):
    doc_ref.update(data)

    return True

def add_to_stash(key,data):
    bank,_ = key.split('_')
    print(bank)

    doc_ref.collection('Stash').document(bank).set(data)

    return True

def add_record(key, dt, data):

    bank, account = key.split('_')
    print(bank,account)
    doc_ref.collection(key).document(dt).set(data)

    return True

if __name__ == '__main__':
    ## Show getting certain records
    print("Show getting certain records")
    print(table.all(formula="Rating < 5", sort=['-Rating']))

    ## Show getting a single record
    print("Show getting a single record")

    # Replace a record
    print("Replace a record")
    name = "Test Message"
    record_id = table.first(formula=f"Book='{name}'")['id']
    table.update(record_id, {"Rating": 5})

    ## Show all records
    print("All records!")
    print(table.all())