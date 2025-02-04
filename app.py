from flask import Flask, jsonify, request
from flask_restful import Api, Resource
from flasgger import Swagger

import fb_manager
from formatter import *

app = Flask(__name__)
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

        if name == 'ritariya' and key == '210102':
            # Get all the books
            books = fb_manager.get_all_records()
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





        return "S", 200


class AddRecord(Resource):
    def post(self):
        """
        This method responds to the POST request for adding a new record to the DB table.
        ---
        tags:
        - Records
        parameters:
            - in: body
              name: body
              required: true
              schema:
                id: BookReview
                required:
                  - Book
                  - Rating
                properties:
                  Book:
                    type: string
                    description: the name of the book
                  Rating:
                    type: integer
                    description: the rating of the book (1-10)
        responses:
            200:
                description: A successful POST request
            400: 
                description: Bad request, Some error occurred
        """

        data = request.json
        key, json, time = get_msg_to_json(data)

        if key is None or key == '':
            print(f"\n\nSkipped Record : {data}\n\n")
            return {"message" : f"Skipped Record : {data}"}

        if len(json) == 0:
            path = f"Ritam/Stash/{key.split('_')[0]}/{time}"
            success = fb_manager.add_to_stash(path,data)
        # Call the add_record function to add the record to the DB table
        else:
            path = f"Ritam/{key.replace('_', '/')}/{time}"
            success = fb_manager.add_record(path, json)
        if success:
            return {"message": "Record added successfully"}, 200
        else:
            return {"message": "Failed to add record"}, 500
        


api.add_resource(AddRecord, "/add-record")
api.add_resource(Records, "/records")
# api.add_resource(UppercaseText, "/uppercase")

if __name__ == "__main__":
    app.run(debug=True)