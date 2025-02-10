
from datetime import datetime
import numpy as np

TAGS_LIST = {
    'RITAM CHATTERJEE' : [['Self Transfer'],'*'],
    'RITAM CHATTERJE' : [['Self Transfer'],'*'],
    'ritam2021@ybl' : [['Self Transfer'],'*'],
    'ritam.hdfc@ybl' : [['Self Transfer'],'*'],
    'chatterjee.ritam1@ybl' : [['Self Transfer'],'*'],
    'Ansad V' : [['Tapri','Snacks'],'Debit'],
    'gpay-11251552163@okbizaxis' : [['MomsKitchen','Snacks'],'Debit'],
    'q987271354@ybl' : [['Tapri','Snacks'],'Debit'],
    'Cheq' : [['CC Repayment'],'Debit'],
    'OneCard' : [['CC Repayment'],'Debit'],
    'NACH' : [['SIP','Savings'],'Debit'],
    "VIGNESH FAST FOODS" : [['Asha Tiffins'],'Debit']
}

def parseMessage(bank, msg, time):
    msg_json = {}
    key = ''
    msg = msg.replace('\n', ' ').replace('\r', '')
    if 'HDFC' in bank.upper():
        BNK = 'HDFC'
        if 'Txn Rs.' in msg and 'HDFC Bank Card' in msg and 'UPI' in msg:
            amount, rest = msg.split('Txn Rs.')[1].split(' On HDFC Bank Card ')
            account, rest = rest.split(' At ')
            to, rest = rest.split(' by ')
            mode, ref = rest.split(" On")[0].split(' ')
            msg_json = {
                'type' : 'Debit',
                'mode' : mode,
                'accountType' : 'Credit Card',
                'to_from' : to,
                'account' : account,
                'amount' : amount,
                'refNo' : ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
            # print(msg_json)
        elif 'Used Rs' in msg and 'On HDFCBank Card' in msg and 'UPI' in msg:
            amount, rest = msg.split('Used Rs')[1].split(' On HDFCBank Card ')
            account, rest = rest.split(' At ')
            to, rest = rest.split(' by ')
            mode, ref = rest.split(" On")[0].split(' ')
            msg_json = {
                'type': 'Debit',
                'mode': mode,
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Sent Rs.' in msg and 'From HDFC Bank A/C x' in msg:
            amount, rest = msg.split('Sent Rs.')[1].split(' From HDFC Bank A/C x')
            account, rest = rest.split(' To ')
            to, rest = rest.split(' On ')
            ref = rest.split('Ref ')[1].split(' Not You?')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'UPI', # Need to check
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'HDFC Bank Cardmember, Online Payment of Rs.' in msg and 'was credited to your card ending' in msg:
            amount, rest = msg.split('HDFC Bank Cardmember, Online Payment of Rs.')[1].split(' vide Ref# ')
            ref, rest = rest.split(' was credited to your card ending ')
            account = rest.split(' On ')[0]
            msg_json = {
                'type': 'Credit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'Self',
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Rs.' in msg and 'credited to HDFC Bank A/c x' in msg:
            amount, rest = msg.split('Rs.')[1].split(' credited to HDFC Bank A/c xx')
            account, rest = rest.split(' on ')
            mode, to, _, ref = rest.split(' from ')[1].split(' ')
            msg_json = {
                'type': 'Credit',
                'mode': mode,
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref[:-1],
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Rs.' in msg and ' spent on HDFC Bank Card x' in msg:
            amount, rest = msg.split('Rs.')[1].split(' spent on HDFC Bank Card x')
            account, rest = rest.split(' at ')
            to, _ = rest.split(' on ')
            msg_json = {
                'type': 'Debit',
                'mode': 'Card',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'DEAR HDFCBANK CARDMEMBER, PAYMENT OF Rs. ' in msg and ' RECEIVED TOWARDS YOUR CREDIT CARD ENDING WITH ' in msg:
            amount, rest = msg.split('DEAR HDFCBANK CARDMEMBER, PAYMENT OF Rs. ')[1].split(' RECEIVED TOWARDS YOUR CREDIT CARD ENDING WITH ')
            account, rest = rest.split(' ON ')
            msg_json = {
                'type': 'Credit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'Self',
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Rs.' in msg and ' withdrawn from HDFC Bank Card x' in msg:
            amount, rest = msg.split('Rs.')[1].split(' withdrawn from HDFC Bank Card x')
            account, rest = rest.split(' at ')
            to = rest.split(' on ')
            msg_json = {
                'type': 'Debit',
                'mode': 'Withdrawal',
                'accountType': 'Savings',
                'to_from': 'Self',
                'tags': ['ATM'],
                'account': '5808' if account == '2148' else account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{'5808' if account == '2148' else account}"
        elif 'Update! INR ' in msg and ' deposited in HDFC Bank A/c XX' in msg:
            amount, rest = msg.split("Update! INR ")[1].split(" deposited in HDFC Bank A/c XX")
            account, rest = rest.split(" on ")
            mode,rest = rest.split(" for ")[1].split(" Cr-")
            ref, to, _ = rest.split("-",maxsplit=2)
            msg_json = {
                'type': 'Credit',
                'mode': mode,
                'accountType': 'Savings',
                'to_from': to,
                'tags': ['Salary'],
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'HDFC Bank Cardmember, Payment of Rs ' in msg and ' was credited to your card ending ' in msg:
            amount, rest = msg.split("HDFC Bank Cardmember, Payment of Rs ")[1].split(" was credited to your card ending ")
            account, rest = rest.split(" on ")
            msg_json = {
                'type': 'Debit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'Self',
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Dear Customer, Rs.' in msg and ' is debited from A/c XXXX' in msg and ' for BillPay/Credit Card payment via HDFC Bank NetBanking. ' in msg:
            amount, rest = msg.split("Dear Customer, Rs.")[1].split(" is debited from A/c XXXX")
            account, rest = rest.split(" for BillPay/Credit Card payment via HDFC Bank NetBanking. ")
            msg_json = {
                'type': 'Debit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'Credit Card',
                'tags': ['CC Repayment'],
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Amt Sent Rs.' in msg and ' From HDFC Bank A/C *' in msg:
            amount, rest = msg.split("Amt Sent Rs.")[1].split(" From HDFC Bank A/C *")
            account, rest = rest.split(" To ")
            to, rest = rest.split(" On ")
            ref, rest = rest.split(' Ref ')[1].split(' Not You?')
            msg_json = {
                'type': 'Debit',
                'mode': 'UPI',
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Rs. ' in msg and ' credited to a/c XXXXXX' in msg:
            amount, rest = msg.split("Rs. ")[1].split(" credited to a/c XXXXXX")
            account, rest = rest.split(" on ")
            to, rest = rest.split(' to VPA ')[1].split(' (UPI')
            ref, _ = rest.split(' Ref No ')[1].split(').')
            msg_json = {
                'type': 'Credit',
                'mode': 'UPI',
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Your UPI transaction of Rs ' in msg and ' has been reversed in your HDFC Bank Credit Card due to technical problem (' in msg:
            amount, rest = msg.split("Your UPI transaction of Rs ")[1].split(" has been reversed in your HDFC Bank Credit Card due to technical problem (")
            ref, rest = rest.split("UPI Ref no. ")[1].split(')')
            msg_json = {
                'type': 'Credit',
                'mode': 'Refund',
                'accountType': 'Credit Card',
                'to_from': 'Self',
                'account': '6484',
                'tags': ['Refund'],
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = 'Refunds_NA'
        else:
                if ('OTP IS' not in msg.upper() and 'AMT DUE' not in msg.upper() and 'DUE AMT' not in msg.upper()
                        and 'E-MANDATE!' not in msg.upper() and 'LOAN' not in msg.upper() and 'BREAKING NEWS!'
                        not in msg.upper() and 'OFFER VALID' not in msg.upper() and 'EMI' not in msg.upper()
                        and 'CREDIT LIMIT' not in msg.upper() and 'CARD LIMIT' not in msg.upper()):
                    key = BNK + '_NA'
                    pass
    if 'SBI' in bank.upper():
        BNK = 'SBI'
        if 'Dear SBI User, your A/c X' in msg and '-credited by Rs.' in msg and ' transfer from ' in msg:
            account, rest = msg.split('Dear SBI User, your A/c X')[1].split('-credited by Rs.')
            amount, rest = rest.split(' on ')
            to, rest = rest.split(' transfer from ')[1].split(' Ref No ')
            ref = rest.split(' -SBI')[0]
            msg_json = {
                'type': 'Credit',
                'mode': 'UPI',
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Dear UPI user A/C X' in msg and ' debited by ' in msg and ' trf to ' in msg:
            account, rest = msg.split('Dear UPI user A/C X')[1].split(' debited by ')
            amount, rest = rest.split(' on date ')
            to, rest = rest.split(' trf to ')[1].split(' Refno ')
            ref = rest.split('.')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'UPI',
                'accountType': 'Savings',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Dear Customer, Your A/C XXXXX' in msg and ' has a debit by ' in msg and '. Avl Bal Rs ' in msg:
            account, rest = msg.split('Dear Customer, Your A/C XXXXX')[1].split(' has a debit by ')
            to, rest = rest.split(' of Rs ')
            amount = rest.split(' on ')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'BANK',
                'accountType': 'Savings',
                'to_from': to,
                'account': account[2:],
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account[2:]}"
        elif 'Dear SBI UPI User, ur A/cX' in msg and ' credited by Rs' in msg:
            account, rest = msg.split("Dear SBI UPI User, ur A/cX")[1].split(" credited by Rs")
            amount, rest = rest.split(" on ")
            ref, rest = rest.split('Ref no ')[1].split(')')
            msg_json = {
                'type': 'Credit',
                'mode': 'N/A',
                'accountType': 'Savings',
                'to_from': 'N/A',
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Dear SBI Customer, Rs.' in msg and ' withdrawn at ' in msg:
            amount, rest = msg.split("Dear SBI Customer, Rs.")[1].split(" withdrawn at ")
            to, rest = rest.split(" from A/cX")
            account, rest = rest.split(' on ')
            ref, rest = rest.split(' Transaction Number ')[1].split('.',maxsplit=1)
            msg_json = {
                'type': 'Debit',
                'mode': 'Withdrawal',
                'tags': ['ATM'],
                'accountType': 'Savings',
                'to_from': 'Self',
                'account': account,
                'amount': amount.strip(),
                'refNo': ref,
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        else:
            if ('OTP IS' not in msg.upper() and 'AMT DUE' not in msg.upper() and 'DUE AMT' not in msg.upper()
                    and 'E-MANDATE!' not in msg.upper() and 'LOAN' not in msg.upper() and 'BREAKING NEWS!'
                    not in msg.upper() and 'OFFER VALID' not in msg.upper() and 'EMI' not in msg.upper()
                    and 'CREDIT LIMIT' not in msg.upper() and 'CARD LIMIT' not in msg.upper()):
                # print(msg)
                key = BNK + '_NA'
                pass
    if 'ONECRD' in bank.upper():
        BNK = 'ONE'
        if 'card ending XX6901.' in msg and "You've fueled up for Rs." in msg:
            amount, rest = msg.split("You've fueled up for Rs.  ")[1].split(' at ')
            to = rest.split(' on card ending XX6901.')[0]
            account = '6901'
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'tags' : ['Fuel'],
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'card ending XX6901.' in msg and 'Youve booked a blockbuster entertainment for Rs.' in msg:
            amount, rest = msg.split('Youve booked a blockbuster entertainment for Rs.  ')[1].split(' on ')
            to = rest.split(' with card ending XX6901.')[0]
            account = '6901'
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif "You've hand-picked " in msg and ' on card ending XX' in msg:
            amount, rest = msg.split(' for Rs. ')[1].split(' at ')
            to, rest = rest.split(' on card ending XX')
            account, rest = rest.split(' & ')
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'tags': ['Shopping'],
                'to_from': to,
                'account': '6901',
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif "Hola! that was sweet. We have received payment against your OneCard for Rs. " in msg:
            amount,_ = msg.split('Hola! that was sweet. We have received payment against your OneCard for Rs. ')[1].split(' on ')
            account = '6901'
            msg_json = {
                'type': 'Credit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'self',
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Hi, We have received a refund of Rs.' in msg and ' on your Federal One Credit Card. ' in msg:
            amount, rest = msg.split('Hi, We have received a refund of Rs.')[1].split(" from ")
            to, _ = rest.split(' on your Federal One Credit Card. ')
            account = '6901'
            msg_json = {
                'type': 'Credit',
                'mode': 'Refund',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"Refunds_{account}"
        elif 'A payment of Rs.' in msg and ' has been initiated against your OneCard bill & ' in msg:
            amount, rest = msg.split('A payment of Rs.')[1].split(' has been initiated against your OneCard bill & ')
            account = '6901'
            msg_json = {
                'type': 'Credit',
                'mode': 'Repayment',
                'accountType': 'Credit Card',
                'to_from': 'N/A',
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif "You've made a purchase of Rs. " in msg and ' on card ending XX' in msg:
            amount, rest = msg.split("You've made a purchase of Rs. ")[1].split(' at ')
            to, rest = rest.split(' on card ending XX')
            account = '6901'
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif "That was a delicious purchase of Rs." in msg and ' on card ending XX' in msg:
            amount, rest = msg.split("That was a delicious purchase of Rs.")[1].split(' at ')
            to, rest = rest.split(' on card ending XX')
            account = '6901'
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': 'N/A',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        else:
            # print(bank,msg)
            key = BNK + '_NA'
            pass

    if 'IDFC' in bank.upper():
        BNK = 'IDFC'
        if 'Happy Shopping! INR ' in msg and ' spent on your IDFC FIRST Bank Credit Card ending XX' in msg:
            amount, rest = msg.split('Happy Shopping! INR ')[1].split(' spent on your IDFC FIRST Bank Credit Card ending XX')
            account, rest = rest.split(' at ',maxsplit=1)
            to = rest.split(' on ')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Transaction Successful! INR ' in msg and ' spent on your IDFC FIRST Bank Credit Card ending ' in msg:
            amount, rest = msg.split('Transaction Successful! INR ')[1].split(' spent on your IDFC FIRST Bank Credit Card ending XX')
            account, rest = rest.split(' at ',maxsplit=1)
            to = rest.split(' on ')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'account': account,
                'amount': amount.strip(),
                'refNo': '',
                 'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"
        elif 'Fueled Up! INR ' in msg and ' spent on your IDFC FIRST Bank Credit Card XX' in msg:
            amount, rest = msg.split('Fueled Up! INR ')[1].split(' spent on your IDFC FIRST Bank Credit Card XX')
            account, rest = rest.split(' at ',maxsplit=1)
            to = rest.split(' on ')[0]
            msg_json = {
                'type': 'Debit',
                'mode': 'Transaction',
                'accountType': 'Credit Card',
                'to_from': to,
                'tags': ['Fuel'],
                'account': account,
                'amount': amount.strip(),
                'refNo': '',
                'time': time.strftime("%d-%b, %I:%M %p")
            }
            key = f"{BNK}_{account}"

        else:
            # print(bank,msg)
            key = BNK + '_NA'
            pass


    if len(msg_json) > 0:
        msg_json['gps'] = ""
        if 'tags' not in msg_json:
            msg_json['tags'] = []

        k = msg_json['to_from'].strip()
        if k in TAGS_LIST:
            tags, type = TAGS_LIST[k]
            print(tags,msg_json['tags'],type)
            if type == '*':
                msg_json['tags'].extend(tags)
                msg_json['tags'] = list(set(msg_json['tags']))
            elif msg_json['type'] == type:
                msg_json['tags'].extend(tags)
                msg_json['tags'] = list(set(msg_json['tags']))

    return key, msg_json


paymentInfo = {
    'SBI' : {},
    'HDFC' : {},
    'IDFC' : {},
    'ONE' : {},
    'Refunds' : []
}


z = 0

root = []

def get_msg_to_json(x, format = "%d/%m/%Y, %I:%M %p"):

    if True in [K in x.get('address').upper() for K in paymentInfo.keys()]:
        dt_str = x.get('readable_date').replace('Sept','Sep')
        datetime_object = datetime.strptime(dt_str,format)

        body = x.get('body')
        bank_name = x.get('address')
        key, json_body = parseMessage(bank_name,body, datetime_object)
        return key, json_body, datetime_object.replace(second=np.random.randint(0,60))
        # return key, json_body, datetime_object
    else:
        return None, None, None