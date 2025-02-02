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
# class Records(Resource):
#     def get(self):
#         """
#         This method responds to the GET request for returning a number of books.
#         ---
#         tags:
#         - Records
#         parameters:
#             - name: count
#               in: query
#               type: integer
#               required: false
#               description: The number of books to return
#             - name: sort
#               in: query
#               type: string
#               enum: ['ASC', 'DESC']
#               required: false
#               description: Sort order for the books
#         responses:
#             200:
#                 description: A successful GET request
#                 schema:
#                     type: object
#                     properties:
#                         books:
#                             type: array
#                             items:
#                                 type: object
#                                 properties:
#                                     title:
#                                         type: string
#                                         description: The title of the book
#                                     author:
#                                         type: string
#                                         description: The author of the book
#         """
#
#         count = request.args.get('count')  # Default to returning 10 books if count is not provided
#         sort = request.args.get('sort')
#
#         # Get all the books
#         books = fb_manager.get_all_records(count=count, sort=sort)
#
#         return {"books": books}, 200
#
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
        key, json = get_msg_to_json(data)
        # Check if 'Book' and 'Rating' are present in the request body
        print("Starting FB")
        if len(json) == 0:
            success = fb_manager.add_to_stash(key,data)
        # Call the add_record function to add the record to the DB table
        else:
            success = fb_manager.add_record(key,data['readable_date'], json)
        if success:
            return {"message": "Record added successfully"}, 200
        else:
            return {"message": "Failed to add record"}, 500
        


api.add_resource(AddRecord, "/add-record")
# api.add_resource(Records, "/records")
# api.add_resource(UppercaseText, "/uppercase")

if __name__ == "__main__":
    app.run(debug=True)