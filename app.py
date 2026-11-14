from flask import Flask, jsonify, request
from flask_restful import Api, Resource
from flasgger import Swagger
import urllib.parse
from datetime import datetime
import random
import string

import fb_manager
from fb_manager import verify_creds, add_new_user, get_users, update_memo
from formatter import get_msg_to_json
from llm_parser import should_skip, scrub_sms, parse_with_llm, reconstruct, detect_bank
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, allow_headers="*")
api = Api(app)

swagger = Swagger(app)
#
# class UppercaseText(Resource):
#     def get(self):
#         """
#         This method responds to the GET request for this endpoint and returns the data in uppercase.
#         ---
#         tags:
#         - Text Processing
#         parameters:
#             - name: text
#               in: query
#               type: string
#               required: true
#               description: The text to be converted to uppercase
#         responses:
#             200:
#                 description: A successful GET request
#                 content:
#                     application/json:
#                       schema:
#                         type: object
#                         properties:
#                             text:
#                                 type: string
#                                 description: The text in uppercase
#         """
#         text = request.args.get('text')
#
#         return jsonify({"text": text.upper()})
#
class Records(Resource):
    def get(self):
        """
        This method responds to the GET request for returning a number of books.
        ---
        tags:
        - Records
        parameters:
            - name: count
              in: query
              type: integer
              required: false
              description: The number of books to return
            - name: sort
              in: query
              type: string
              enum: ['ASC', 'DESC']
              required: false
              description: Sort order for the books
        responses:
            200:
                description: A successful GET request
                schema:
                    type: object
                    properties:
                        books:
                            type: array
                            items:
                                type: object
                                properties:
                                    title:
                                        type: string
                                        description: The title of the book
                                    author:
                                        type: string
                                        description: The author of the book
        """

        since = request.args.get('since')
        user = request.headers.get('user', request.args.get('uname', 'Ritam'))
        books = fb_manager.get_all_records(user, since_timestamp=since)
        return books, 200


class UpdateRecords(Resource):
    def post(self):
        """
        This method responds to the GET request for returning a number of books.
        ---
        tags:
        - Records
        parameters:
            - name: count
              in: query
              type: integer
              required: false
              description: The number of books to return
            - name: sort
              in: query
              type: string
              enum: ['ASC', 'DESC']
              required: false
              description: Sort order for the books
        responses:
            200:
                description: A successful GET request
                schema:
                    type: object
                    properties:
                        books:
                            type: array
                            items:
                                type: object
                                properties:
                                    title:
                                        type: string
                                        description: The title of the book
                                    author:
                                        type: string
                                        description: The author of the book
        """

        data = request.json

        if 'user' in request.headers:
           user = request.headers['user']
        else:
            user = 'Ritam'

        success = fb_manager.update_records(user , data)

        if success:
            return {"message": "Record added successfully"}, 200
        else:
            return {"message": "Failed to add record"}, 500


class AddRecord(Resource):
    def post(self):
        data = request.json
        if not data:
            return {"message": "Empty body"}, 400

        print("\n\n\n",data)    
        address = data.get('address', '')
        body = data.get('body', '')
        readable_date = data.get('readable_date', '')
        request_tags = data.get('tags', [])
        request_gps = data.get('gps', "")
        user = request.headers.get('user', 'Ritam')

        
        
        try:
            try:
                if not readable_date: raise ValueError("Empty date")
                time_id = str(datetime.strptime(readable_date, "%d/%m/%y %I:%M %p").isoformat())
            except:
                 # Fallback timestamp logic if unparseable or empty
                time_id = readable_date.replace('/', '-').replace(' ', '_') if readable_date else str(int(datetime.now().timestamp() * 1000))
                if not time_id: time_id = str(int(datetime.now().timestamp() * 1000))
                
            # Fetch User Settings
            settings = fb_manager.get_settings(user)
            configured_banks = settings.get('configuredBanks', [])
            custom_tags = settings.get('customTags', [])
            categories = settings.get('categories', [])
            categorization_rules = settings.get('categorizationRules', {})
            print("\n\n\nAddress:",address,"\n Body:",body,"\n User:",user,"\n Date: ",readable_date,"\n Time ID: ",time_id, "\n GPS : ",request_gps, "\n Tags : ",request_tags)
            # Validate Bank Presence
            bank_name = detect_bank(address)
            bank_configured = any(b.get('bankName', '').upper() == bank_name.upper() for b in configured_banks)
        
            if not bank_configured:
                stash_data = {
                    "raw": body, 
                    "skip_reason": "needs_review_not_configured",
                    "user": user,
                    "address": address,
                    "readable_date": readable_date,
                    "tags": request_tags,
                    "gps": request_gps
                }
                fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                return {"message": "Skipped: needs_review_not_configured"}, 200

            # Stage 1: Pre-validation
            skip, reason = should_skip(address, body)
            if skip:
                stash_data = {
                    "raw": body, 
                    "skip_reason": reason,
                    "user": user,
                    "address": address,
                    "readable_date": readable_date,
                    "tags": request_tags,
                    "gps": request_gps
                }
                fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                return {"message": f"Skipped: {reason}"}, 200

            print("Not Skipped", bank_name)
            # Stage 2: Parse with LLM (Directly use raw body)
            llm_result = parse_with_llm(
                body, address, readable_date, configured_banks, 
                request_tags, request_gps, custom_tags, categories, categorization_rules
            )

            if llm_result is None:
                # LLM call failed — fallback
                stash_data = {
                    "raw": body, 
                    "skip_reason": "llm_error",
                    "user": user,
                    "address": address,
                    "readable_date": readable_date,
                    "tags": request_tags,
                    "gps": request_gps
                }
                fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                return {"message": "Stashed: LLM error"}, 200

            if not llm_result.get("is_transaction"):
                stash_data = {
                    "raw": body, 
                    "skip_reason": "llm_classified_non_transaction",
                    "user": user,
                    "address": address,
                    "readable_date": readable_date,
                    "tags": request_tags,
                    "gps": request_gps
                }
                fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                return {"message": "Skipped: not a transaction"}, 200

            print("LLM Result : ",llm_result)
            transaction = llm_result # Directly use LLM result
            account = transaction.get("account", "UNKNOWN")
            
            if transaction.get('gps','') == '':
                transaction['gps'] = request_gps
            # Validate Account Specifics
            # Find the exact configuration match (Primary or Linked Card)
            target_config = None
            extracted_acc = str(account).strip()
            configs_for_bank = [b for b in configured_banks if b.get('bankName', '').upper() == bank_name.upper()]
            
            for config in configs_for_bank:
                primary_tail = config.get('accountDigits', '').strip()
                linked_cards = config.get('linkedCards', {}) # Map: {digits: nickname}
                
                # Check if matches primary
                if primary_tail and extracted_acc.endswith(primary_tail):
                    target_config = config
                    break
                
                # Check if matches any linked card
                matched_card_nickname = None
                for card_digits, nickname in linked_cards.items():
                    if extracted_acc.endswith(str(card_digits).strip()):
                        matched_card_nickname = nickname
                        break
                
                if matched_card_nickname:
                    target_config = config
                    # Route to primary account
                    account = primary_tail if primary_tail else account
                    # Update transaction object
                    transaction['account'] = account
                    if "Debit Card Transaction" not in transaction.get('tags', []):
                        transaction.setdefault('tags', []).append("Debit Card Transaction")
                    if matched_card_nickname and matched_card_nickname not in transaction.get('tags', []):
                        transaction.setdefault('tags', []).append(matched_card_nickname)
                    break

            has_specific_tails = any(bool(b.get('accountDigits', '').strip()) for b in configs_for_bank)
            
            if has_specific_tails and not target_config:
                  stash_data = {
                      "raw": body, 
                      "skip_reason": "needs_review_not_configured_account",
                      "user": user,
                      "address": address,
                      "readable_date": readable_date,
                      "tags": request_tags,
                      "gps": request_gps
                  }
                  fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                  return {"message": "Skipped: needs_review_not_configured_account"}, 200

            
            # Ensure amount is a number if possible
            try:
                if isinstance(transaction.get('amount'), str):
                     transaction['amount'] = float(transaction['amount'].replace(',', ''))
            except:
                pass

            # Save to Firestore at /{user}/{bank}/{account}/{timestamp}
            fb_manager.add_record(f"{user}/{bank_name}/{account}/{time_id}", transaction)
            return {"message": "Record added successfully"}, 200
        except Exception as e:
            print(f"CRITICAL ERROR in AddRecord: {e}")
            # If anything crashes, try to stash the message as a fallback
            try:
                stash_time_id = readable_date.replace('/', '-').replace(' ', '_') if readable_date else str(int(datetime.now().timestamp()))
                fallback_stash = {
                    "raw": body,
                    "skip_reason": f"system_error_{str(e)[:50]}",
                    "user": user,
                    "address": address,
                    "readable_date": readable_date
                }
                fb_manager.add_to_stash(f"{user}/Stash/{address}/{stash_time_id}", fallback_stash)
            except:
                pass
            return {"message": f"Server Error: {str(e)}"}, 500
        
class ImportBatch(Resource):
    def get(self):
        success = True
        import xml.etree.ElementTree as ET

        tree = ET.parse('sms.xml')

        root = tree.getroot()
        stash = []
        records = []
        for x in root.iter():
            if x.tag !='sms':
                continue
            key, json, time = get_msg_to_json(x,"%d-%b-%Y %I:%M:%S %p")
            if key is None or key == '':
                print(f"\n\nSkipped Record : {x.get('body')}\n\n")
                continue

            if len(json) == 0:
                rec = {'address' : x.get('address'),'body' : x.get('body'),'readable_date':x.get('readable_date')}
                path = f"Ritam/Stash/{key.split('_')[0]}/{time}"
                # success = fb_manager.add_to_stash(path, x)
                stash.append([path,rec])
            else:
                print(time, json['refNo'],x.get('readable_date'))
                path = f"Ritam/{key.replace('_', '/')}/{time}"
                # success = fb_manager.add_record(path, json)
                records.append([path,json])

        # print(records)
        # success = fb_manager.import_all_from_xml(records,stash)

        if success:
            return "Done", 200
        return "Error", 500


class Wake(Resource):
    def get(self):
        success = True

        if success:
            return "Woke-up, Thank u :-)", 200
        return "Error", 500

class UpdateMemo(Resource):
    def post(self):
        data = request.json
        user = request.headers.get('User', 'Ritam')
        success = fb_manager.update_memo(user, data)
        if success:
            return {"message": "Success"}, 200
        return {"message": "Error"}, 500

class Authenticate(Resource):
    def get(self):
        username = request.headers.get('Username', '')
        password = request.headers.get('Password', '')
        success = verify_creds(username, password)
        if success:
            return "User Authenticated!", 200
        return "Error", 500

class SignUp(Resource):
    def post(self):
        data = request.json
        success, message = add_new_user(data)
        if success:
            return {'message':"User Added!"}, 200
        if message == 404:
            return {'message':'User Exists!'}, 404
        return {'message':'Error'}, 500

class GetUsers(Resource):
    def get(self):
        userList = get_users()
        return userList

class Settings(Resource):
    def get(self):
        user = request.headers.get('user', 'Ritam')
        data = fb_manager.get_settings(user)
        return data, 200

    def post(self):
        user = request.headers.get('user', 'Ritam')
        data = request.json
        success = fb_manager.update_settings(user, data)
        if success:
            return {"message": "Settings updated successfully"}, 200
        return {"message": "Failed to update settings"}, 500

class Stash(Resource):
    def get(self):
        user = request.headers.get('user', request.args.get('uname', 'Ritam'))
        since = request.args.get('since')
        stash = fb_manager.get_stash(user, since_timestamp=since)
        return stash, 200

    def delete(self):
        user = request.headers.get('user', 'Ritam')
        address = request.args.get('address')
        time_id = request.args.get('id')
        if not address or not time_id:
            return {"message": "Missing address or id"}, 400
        success = fb_manager.delete_stash_item(user, address, time_id)
        if success:
            return {"message": "Item deleted from stash"}, 200
        return {"message": "Failed to delete item"}, 500

    def post(self):
        user = request.headers.get('user', 'Ritam')
        data = request.json
        old_address = request.args.get('address')
        old_id = request.args.get('id')
        
        new_address = data.get('address')
        new_id = data.get('id')
        
        if not new_address or not new_id:
            return {"message": "Missing new address or id"}, 400
            
        # If path changed, delete old one
        if old_address and old_id and (old_address != new_address or old_id != new_id):
            fb_manager.delete_stash_item(user, old_address, old_id)
            
        fb_manager.add_to_stash(f"{user}/Stash/{new_address}/{new_id}", data)
        return {"message": "Stash item updated"}, 200

class ClearStash(Resource):
    def delete(self):
        user = request.headers.get('user', 'Ritam')
        success = fb_manager.clear_stash(user)
        if success:
            return {"message": "All items deleted from stash"}, 200
        return {"message": "Failed to clear stash"}, 500

class ManualRecord(Resource):
    def post(self):
        user = request.headers.get('user', 'Ritam')
        data = request.json
        bank = data.get('bank', 'Unknown')
        account = data.get('account', 'Manual')
        amount = data.get('amount', 0)
        to_from = data.get('to_from', 'N/A')
        trans_type = data.get('type', 'Debit')
        tags = data.get('tags', [])
        category = data.get('category', 'Miscellaneous')
        date_str = data.get('date') 

        ref_no = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        
        try:
            # Try to use provided date for time_id
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            time_id = dt.isoformat()
            # Format time as a human-readable string (same as SMS-parsed transactions)
            readable_time = dt.strftime('%d %b, %I:%M %p').lstrip('0')
        except:
            dt = datetime.now()
            time_id = dt.isoformat()
            readable_time = date_str or dt.strftime('%d %b, %I:%M %p').lstrip('0')

        transaction = {
            "type": trans_type,
            "mode": "Manual",
            "accountType": data.get('accountType', 'Savings'),
            "account": account,
            "to_from": to_from,
            "amount": amount,
            "refNo": ref_no,
            "time": readable_time,
            "tags": tags,
            "category": category,
            "gps": "",
            "is_manual": True
        }

        path = f"{user}/{bank}/{account}/{time_id}"
        fb_manager.add_record(path, transaction)
        return {"message": "Manual record added", "time_id": time_id}, 200

api.add_resource(AddRecord, "/add-record")
api.add_resource(Records, "/records")
api.add_resource(UpdateRecords, "/update-records")
api.add_resource(ImportBatch, "/add-batch")
api.add_resource(Wake, "/wake-up")
api.add_resource(Settings, "/settings")
api.add_resource(Authenticate, "/auth")
api.add_resource(SignUp, "/sign-up")
api.add_resource(GetUsers, "/get_usernames")
api.add_resource(UpdateMemo, "/update-memo")
api.add_resource(Stash, "/stash")
api.add_resource(ClearStash, "/stash/clear")
api.add_resource(ManualRecord, "/manual-record")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)