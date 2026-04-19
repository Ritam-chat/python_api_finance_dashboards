from flask import Flask, jsonify, request
from flask_restful import Api, Resource
from flasgger import Swagger
import urllib.parse
from datetime import datetime

import fb_manager
from formatter import get_msg_to_json
from llm_parser import should_skip, scrub_sms, parse_with_llm, reconstruct, detect_bank
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app)
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

        name = request.args.get('uname')
        key = request.args.get('key')
        user = request.headers['user']
        if name == 'ritariya' and key == '210102':
            books = fb_manager.get_all_records(user)
        else:
            return "Unable to Authenticate", 500 
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

        address = data.get('address', '')
        body = data.get('body', '')
        readable_date = data.get('readable_date', '')
        user = request.headers.get('user', 'Ritam')
        
        try:
            time_id = str(datetime.strptime(readable_date, "%d/%m/%y %I:%M %p").isoformat())
        except:
             # Fallback timestamp logic if unparseable
            time_id = readable_date.replace('/', '-').replace(' ', '_')

        # Fetch User Settings
        settings = fb_manager.get_settings(user)
        configured_banks = settings.get('configuredBanks', [])

        # Validate Bank Presence
        bank_name = detect_bank(address)
        bank_configured = any(b.get('bankName', '').upper() == bank_name.upper() for b in configured_banks)
        
        if not bank_configured:
            stash_data = {"raw": body, "skip_reason": "needs_review_not_configured"}
            fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
            return {"message": "Skipped: needs_review_not_configured"}, 200

        # Stage 1: Pre-validation
        skip, reason = should_skip(address, body)
        if skip:
            stash_data = {"raw": body, "skip_reason": reason}
            fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
            return {"message": f"Skipped: {reason}"}, 200

        # Stage 2: Scrub
        scrubbed_body, tokens = scrub_sms(body)

        # Stage 3: LLM parse
        llm_result = parse_with_llm(scrubbed_body, address, readable_date)

        if llm_result is None:
            # LLM call failed — fallback
            stash_data = {"raw": body, "skip_reason": "llm_error"}
            fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
            return {"message": "Stashed: LLM error"}, 200

        if not llm_result.get("is_transaction"):
            stash_data = {"raw": body, "skip_reason": "llm_classified_non_transaction"}
            fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
            return {"message": "Skipped: not a transaction"}, 200

        # Reconstruct
        transaction = reconstruct(llm_result, tokens)
        account = transaction.get("account", "UNKNOWN")

        # Validate Account Specifics
        # Only reject if the user HAS configured an account tail for this bank, and it DOES NOT match.
        configs_for_bank = [b for b in configured_banks if b.get('bankName', '').upper() == bank_name.upper()]
        
        # If any configs for this bank have a specific account tail, check if we match it.
        # If all configs for this bank have blank account tails, we assume all accounts are accepted.
        has_specific_tails = any(bool(b.get('accountDigits', '').strip()) for b in configs_for_bank)
        
        if has_specific_tails:
             # Check if our extracted `account` ends with any of the configured tails
             matched_tail = any(account.endswith(b.get('accountDigits', '').strip()) for b in configs_for_bank if b.get('accountDigits', '').strip())
             if not matched_tail:
                  stash_data = {"raw": body, "skip_reason": "needs_review_not_configured_account"}
                  fb_manager.add_to_stash(f"{user}/Stash/{address}/{time_id}", stash_data)
                  return {"message": "Skipped: needs_review_not_configured_account"}, 200
        
        # Save to Firestore at /{user}/{bank}/{account}/{timestamp}
        fb_manager.add_record(f"{user}/{bank_name}/{account}/{time_id}", transaction)
        return {"message": "Record added successfully"}, 200
        
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

api.add_resource(AddRecord, "/add-record")
api.add_resource(Records, "/records")
api.add_resource(UpdateRecords, "/update-records")
api.add_resource(ImportBatch, "/add-batch")
api.add_resource(Wake, "/wake-up")
api.add_resource(Settings, "/settings")

if __name__ == "__main__":
    app.run(debug=True)