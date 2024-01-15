from flask import Flask, request, jsonify, abort
from flask_swagger_ui import get_swaggerui_blueprint
import mysql
import time
from mysql.connector.cursor_cext import CMySQLCursor
from pydantic import BaseModel, ValidationError,EmailStr, Field,confloat
from passlib.hash import pbkdf2_sha256
from datetime import datetime
from jose import JWTError, jwt
import secrets
from typing import Optional
import json
from flask_socketio import SocketIO, emit,disconnect
import threading
import base64
from ultralytics import YOLO
from support_methods import license_formatting_ar,license_formatting_en,carAndPositionDetect,colorDetect
import cv2
import numpy as np
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
import scheduler
from apscheduler.triggers.interval import IntervalTrigger
app = Flask(__name__)
socketio = SocketIO(app)
scheduler = BackgroundScheduler(timezone="Asia/Riyadh")

SWAGGER_URL = '/api/docs'  # URL for exposing Swagger UI (without trailing '/')
API_URL = '/static/swagger.json'  # file location


swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,  # Swagger UI static files will be mapped to '{SWAGGER_URL}/dist/'
    API_URL,
    config={  # Swagger UI config overrides
        'app_name': "Test application"
    
   
    }
)

app.register_blueprint(swaggerui_blueprint)

#this is for connecting to the database with  project enter your database information here
mysql_success = False
sqlite_success = False

while not (mysql_success and sqlite_success):
    try:
        # MySQL setup
        conn = mysql.connector.connect(
            host='localhost',
            database='project',
            user='root',
            password='2459'
        )
        cursor = conn.cursor(cursor_class=CMySQLCursor, buffered=True)
        cursor.execute("CREATE DATABASE IF NOT EXISTS local_genuine")
        print("MySQL Database created successfully!")

        # MySQL queries for creating tables
        queries = [
            """
            CREATE TABLE IF NOT EXISTS User (
                userid INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255),
                email VARCHAR(255),
                typeofplan VARCHAR(100),
                password VARCHAR(255),
                request_count INT DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS Request (
                request_id INT AUTO_INCREMENT PRIMARY KEY,
                userid INT,
                vehicle_type VARCHAR(100),
                license_type VARCHAR(100),
                plate_arabic VARCHAR(100),
                plate_english VARCHAR(100),
                confidence FLOAT,
                orientation VARCHAR(50),
                photo_data MEDIUMBLOB,
                request_datetime DATETIME,
                camera_name VARCHAR(255),
                FOREIGN KEY (userid) REFERENCES User(userid),
                FOREIGN KEY (camera_id) REFERENCES Camera(camera_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS Camera (
                camera_id INT AUTO_INCREMENT PRIMARY KEY,
                camera_ip VARCHAR(255),
                raspberrypi_id VARCHAR(255),
                userid INT,
                camera_name VARCHAR(255),
                camera_mode VARCHAR(50), 
                confidence_threshold FLOAT,
                FOREIGN KEY (userid) REFERENCES User(userid)
            )
            """,
        ]

  
        for query in queries:
            cursor.execute(query)

        print("MySQL Database connection and table creation successful!")
      
        mysql_success = True

        # SQLite setup
        local_conn = sqlite3.connect('genuine_local.db', check_same_thread=False)
        local_cursor = local_conn.cursor()
    


        local_cursor.execute('''
            CREATE TABLE IF NOT EXISTS Camera (
                camera_id INTEGER,
                camera_ip VARCHAR(255),
                raspberrypi_id VARCHAR(255),
                userid INTEGER,
                camera_name VARCHAR(255),
                camera_mode VARCHAR(50),
                confidence_threshold FLOAT
            )
        ''')
        local_cursor.execute('''
                    CREATE TABLE IF NOT EXISTS Request(
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTGER, 
                vehicle_type VARCHAR(100),
                license_type VARCHAR(100),
                plate_arabic VARCHAR(100),
                plate_english VARCHAR(100),
                confidence FLOAT,
                orientation VARCHAR(50),
                photo_data BLOB,
                request_datetime TEXT,
                camera_name VARCHAR(255),    
                camera_id INTEGER
            )
        ''')
        # Commit changes and close the connection
        local_conn.commit()
        

        print("SQLite Database and Camera table created successfully!")
        print("SQLite Database connection was successful!")
        sqlite_success = True

    except mysql.connector.Error as mysql_error:
        print("MySQL Connection or setup failed")
        print("MySQL Error:", mysql_error)

    except sqlite3.Error as sqlite_error:
        print("SQLite Connection or setup failed")
        print("SQLite Error:", sqlite_error)

    time.sleep(5)  # Wait 5 seconds before attempting MySQL and SQLite setup again

# Both databases connected successfully, break out of the loop
print("Both MySQL and SQLite databases connected successfully!")

class LoginData(BaseModel):
    username: str
    password: str

class User(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username should have 3-50 characters",
    )
    email: EmailStr = Field(
        ...,
        min_length=6,
        max_length=100,
        description="Email should have 6-100 characters",
    )
    typeofplan: str
    password: str = Field(
        ...,
        min_length=6,
        max_length=50,
        description="Password should have 6-50 characters",
    )
class CameraData(BaseModel):
    camera_id: Optional[str] = None
    camera_name: str
    camera_mode: str
    camera_ip: str
    confidence_threshold: confloat(strict=True, lt=1.0)

#this is for the token 
SECRET_KEY = "245"
ALGORITHM = "HS256"
#this is for the token creation
def create_access_token(*, username: str):
    to_encode = {"username": username}
    # expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
#this is for the token decoding 
def decode_access_token(*, token: str):
    try:
        decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_jwt
    except jwt.PyJWTError:
        return {"message": "Could not decode token"}
#this endpoint for the user registration
@app.route('/user/register', methods=['POST'])
def register_user():
    try:
        user_data = User(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

   
    query_check = "SELECT username FROM User WHERE username = %s"
    cursor.execute(query_check, (user_data.username,))
    existing_user = cursor.fetchone()
    cursor.fetchall()
    if existing_user:
        return jsonify({"message": "Username already exists"})

    hashed_password = pbkdf2_sha256.hash(user_data.password)
    query = "INSERT INTO User (username, email, typeofplan, password) VALUES (%s, %s, %s, %s)"
    values = (user_data.username, user_data.email, user_data.typeofplan, hashed_password)

    try:
        cursor.execute(query, values)
        conn.commit()
        return jsonify({"message": "User registration successful"})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "User registration failed", "error": str(error)})
#this endpoint for the user login
@app.route('/user/login', methods=['POST'])
def login_user():
    try:
        login_data = LoginData(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

   
    query_check = "SELECT password FROM User WHERE username = %s"
    cursor.execute(query_check, (login_data.username,))
    user = cursor.fetchone()
    cursor.fetchall()
    if not user:
        return jsonify({"message": "Username does not exist"})
    
 
    if pbkdf2_sha256.verify(login_data.password, user[0]):
        access_token = create_access_token(username=login_data.username)
        return jsonify({"message": "Login successful", "access_token": access_token})
    else:
        return jsonify({"message": "Incorrect password"})

global camera_ip
# this endpoint for the user camera add
@app.route('/user/camera/add', methods=['POST'])
def add_camera():
    global camera_id, camera_ip, confidence

    camera_id = None  # Define camera_id here

    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"})

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt)

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    cursor.fetchall()
    if not user:
        return jsonify({"message": "User does not exist"})

    userid = user[0]

    try:
        camera_data = CameraData(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

    query = "INSERT INTO Camera (camera_name, camera_mode, camera_ip, confidence_threshold, userid) VALUES (%s, %s, %s, %s, %s)"
    sqlite_query = "INSERT INTO Camera (camera_id, camera_name, camera_mode, camera_ip, confidence_threshold, userid) VALUES (?, ?, ?, ?, ?, ?)"
    values = (camera_data.camera_name, camera_data.camera_mode, camera_data.camera_ip, camera_data.confidence_threshold, userid)
    camera_ip = camera_data.camera_ip
    confidence = camera_data.confidence_threshold
    try:
        cursor.execute(query, values)
        conn.commit()

        camera_id = cursor.lastrowid  # Update the global variable with the last inserted camera_id

        # Insert the same data into the local database
        sqlite_values = (camera_id, camera_data.camera_name, camera_data.camera_mode, camera_data.camera_ip, camera_data.confidence_threshold, userid)
        local_cursor.execute(sqlite_query, sqlite_values)
        local_conn.commit()

        return jsonify({"message": "Camera added successfully", "camera_id": camera_id})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to add camera", "error": str(error)})
#this endpoint for the user camera update
@app.route('/user/camera/update', methods=['PUT'])
def update_camera():
    global connected,ret,confidence
    global connected_cameras
    global camera_ip, registered
    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"})

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt)

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"})
    
    userid = user[0]

    try:
        camera_data = CameraData(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

    query_check = "SELECT * FROM Camera WHERE camera_id = %s AND userid = %s"
    cursor.execute(query_check, (camera_data.camera_id, userid))
    camera = cursor.fetchone()
    if not camera:
        return jsonify({"message": "Camera not found or does not belong to the user"})

    camera_id_to_update = camera_data.camera_id

    query = "UPDATE Camera SET camera_name = %s, camera_mode = %s, confidence_threshold = %s, camera_ip = %s WHERE camera_id = %s"
    sqlite_query = "UPDATE Camera SET camera_name = ?, camera_mode = ?, confidence_threshold = ?, camera_ip = ? WHERE camera_id = ?"
    values = (camera_data.camera_name, camera_data.camera_mode, camera_data.confidence_threshold, camera_data.camera_ip, camera_id_to_update)

    try:
        
        cursor.execute(query, values)
        conn.commit()
        local_cursor.execute(sqlite_query,values)
        local_conn.commit()

        for socket_id, cam_id in connected_cameras.items():
            if cam_id == camera_id_to_update:
                print('Disconnecting Socket ID:', socket_id)
                socketio.server.disconnect(socket_id)
                confidence = camera_data.confidence_threshold
                registered = False
                break

        return jsonify({"message": "Camera updated successfully"})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to update camera", "error": str(error)})
    
#this endpoint for the user camera delete
@app.route('/user/camera/delete', methods=['DELETE'])
def delete_camera():
    global connected,ret,confidence
    global connected_cameras
    global camera_ip
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    data = request.json
    camera_id_to_delete = data.get('camera_id')

    if not camera_id_to_delete:
        return jsonify({"message": "Missing camera_id in the request"}), 400

    try:
        # Check if the camera exists in the local database
        local_cursor.execute("SELECT camera_id FROM Camera WHERE camera_id = ?", (camera_id_to_delete,))
        camera = local_cursor.fetchone()
        if not camera:
            return jsonify({"message": "Camera does not exist in the local database"}), 404

        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        # Now, delete the camera
        delete_query = "DELETE FROM Camera WHERE camera_id = %s"
        sqlite_delete_query = "DELETE FROM Camera WHERE camera_id = ?"
        cursor.execute(delete_query, (camera_id_to_delete,))
        conn.commit()
        local_cursor.execute(sqlite_delete_query, (camera_id_to_delete,))
        local_conn.commit()  # Don't forget the parentheses

        for socket_id, cam_id in connected_cameras.items():
            if cam_id == camera_id_to_delete:
                print('Disconnecting Socket ID:', socket_id)
                socketio.server.disconnect(socket_id)
                connected=False
                ret= False
                break

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")

        return jsonify({"message": "Camera deleted successfully"}), 200

    except mysql.connector.Error as error:
        conn.rollback()
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        return jsonify({"message": "Failed to delete camera", "error": str(error)}), 500
     
    

@app.route('/user/analytics', methods=['GET'])
def user_analytics():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    try:
        # Fetch analytics data related to the user's cameras
        analytics_query = """
            SELECT camera_id, COUNT(*) AS request_count 
            FROM Request 
            WHERE userid = %s 
            GROUP BY camera_id
        """
        cursor.execute(analytics_query, (userid,))
        analytics_data = cursor.fetchall()

        # Example analytics data format
        analytics = []
        for row in analytics_data:
            camera_id, request_count = row
            analytics.append({
                "camera_id": camera_id,
                "request_count": request_count
            })

        return jsonify({"analytics": analytics}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch analytics", "error": str(error)}), 500
    
@app.route('/user/requests_between_periods', methods=['POST'])
def requests_between_periods():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    # Fetching time periods from the request body
    data = request.json
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    try:
        # Convert start_time and end_time strings to datetime objects
        start_time_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        end_time_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')

        # Fetch requests that occurred between the specified time periods
        requests_query = """
            SELECT * FROM Request 
            WHERE userid = %s 
            AND request_datetime >= %s 
            AND request_datetime <= %s
        """
        cursor.execute(requests_query, (userid, start_time_dt, end_time_dt))
        requests_data = cursor.fetchall()

        # Constructing the response with requests between the periods
        requests_between_periods = []
        for row in requests_data:
            request_info = {
                "request_id": row[0],
                "camera_id": row[1],
                "request_datetime":str(row[9]),
               "image": base64.b64encode(row[8]).decode('utf-8') if row[8] else None,
                # Add other columns as needed
            }
            requests_between_periods.append(request_info)

        return jsonify({"requests_between_periods": requests_between_periods}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch requests between periods", "error": str(error)}), 500

@app.route('/user/vehicle_type_percentage', methods=['GET'])
def vehicle_type_percentage():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    try:
        # Fetching vehicle types and their counts for the user
        query = """
            SELECT vehicle_type, COUNT(vehicle_type) as type_count
            FROM Request 
            WHERE userid = %s 
            GROUP BY vehicle_type
        """
        cursor.execute(query, (userid,))
        rows = cursor.fetchall()

        # Constructing the response with vehicle type percentages
        vehicle_types = []
        total_requests = 0

        for row in rows:
            vehicle_type = row[0]
            type_count = row[1]
            total_requests += type_count
            vehicle_types.append({
                'vehicle_type': vehicle_type,
                'percentage': (type_count / total_requests) * 100
            })

        return jsonify({"vehicle_type_percentage": vehicle_types}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch vehicle type percentage", "error": str(error)}), 500


@app.route('/user/car_info', methods=['POST'])
def car_info():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    data = request.json
    plate = data.get('plate')  # Plate value entered by the user

    if not plate:
        return jsonify({"message": "Plate is missing in the request"}), 400

    # Check both columns for the plate
    plate_columns = ["plate_arabic", "plate_english"]

    try:
        # Fetch information related to the entered plate
        car_info_list = []
        for plate_column in plate_columns:
            car_info_query = f"""
                SELECT * FROM Request 
                WHERE userid = %s 
                AND {plate_column} = %s
            """
            cursor.execute(car_info_query, (userid, plate))
            car_info = cursor.fetchall()

            # Constructing the response with car information
            for row in car_info:
                info = {
                    "image": base64.b64encode(row[8]).decode('utf-8') if row[8] else None,
                    "vehicle_type": row[2],  
                    "license_type": row[3],
                    "plate_arabic": row[4],
                    "plate_english": row[5],
                    "datetime": row[9],
                    
                    

                    # Add other columns as needed
                }
                car_info_list.append(info)

        return jsonify({"car_information": car_info_list}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch car information", "error": str(error)}), 500
@app.route('/user/peak_times', methods=['GET'])
def get_peak_times():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    try:
        # Fetching the user ID based on the username
        query_check = "SELECT userid FROM User WHERE username = %s"
        cursor.execute(query_check, (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"message": "User does not exist"}), 404
    
        userid = user[0]

        # Analyzing peak times and non-peak times based on requests
        query = """
            SELECT HOUR(request_datetime) AS hour_slot, COUNT(*) AS request_count
            FROM Request
            WHERE userid = %s
            GROUP BY hour_slot
        """
        cursor.execute(query, (userid,))
        results = cursor.fetchall()
        peak_times = []
        non_peak_times = []

        for result in results:
            hour_slot = result[0]
            request_count = result[1]

            # Convert hour slots to time ranges (assuming hourly intervals)
            time_range = f"{hour_slot}:00 - {hour_slot + 1}:00"

            # Define your threshold for peak and non-peak times
            if request_count >= 10:  # Replace with your threshold value
                peak_times.append(hour_slot)
            else:
                non_peak_times.append(hour_slot)

        # Convert hour slots to human-readable time ranges
        peak_times = convert_to_time_ranges(peak_times)
        non_peak_times = convert_to_time_ranges(non_peak_times)

        return jsonify({
            "peak_times": peak_times,
            "non_peak_times": non_peak_times
        }), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch peak times", "error": str(error)}), 500

# Function to convert hour slots into time ranges
def convert_to_time_ranges(times):
    times.sort()
    ranges = []
    start = None
    prev = None

    for time in times:
        if start is None:
            start = time
            prev = time
        elif prev + 1 == time:
            prev = time
        else:
            if start == prev:
                ranges.append(f"{start}:00")
            else:
                ranges.append(f"{start}:00-{prev + 1}:00")
            start = time
            prev = time

    if start is not None:
        if start == prev:
            ranges.append(f"{start}:00")
        else:
            ranges.append(f"{start}:00-{prev + 1}:00")

    return ranges
@app.route('/user/best_day_in_month', methods=['POST'])
def best_day_in_month():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404

    userid = user[0]

    data = request.json
    month = data.get('month')  # Month provided by the user (e.g., 1 for January)

    try:
        # Get the year and month from the provided value
        year = datetime.now().year  # You might need to handle year input from the user
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1 if month < 12 else 1, 1)  # End of the next month

        # Fetch the number of requests for each day in the month
        query = """
            SELECT DAY(request_datetime) AS request_day, COUNT(*) AS request_count
            FROM Request
            WHERE userid = %s
            AND request_datetime >= %s
            AND request_datetime < %s
            GROUP BY request_day
            ORDER BY request_count DESC
            LIMIT 1
        """
        cursor.execute(query, (userid, start_date, end_date))
        best_day_info = cursor.fetchone()

        if not best_day_info:
            return jsonify({"message": "No requests found for the given month"}), 404

        best_day = best_day_info[0]
        request_count = best_day_info[1]

        return jsonify({
            "best_day": best_day,
            "request_count": request_count
        }), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch best day in the month", "error": str(error)}), 500
    

@app.route('/user/best_month_in_year', methods=['POST'])
def best_month_in_year():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    data = request.json
    year = data.get('year')

    if not year:
        return jsonify({"message": "Year missing in the request"}), 400

    try:
        # Query to find the best month based on the number of requests
        best_month_query = """
            SELECT MONTH(request_datetime) as month, COUNT(*) as request_count
            FROM Request
            WHERE userid = %s AND YEAR(request_datetime) = %s
            GROUP BY MONTH(request_datetime)
            ORDER BY request_count DESC
            LIMIT 1
        """
        cursor.execute(best_month_query, (userid, year))
        best_month_data = cursor.fetchone()

        if not best_month_data:
            return jsonify({"message": "No data found for the given year"}), 404

        best_month_number = best_month_data[0]  # Extract the best month number

        # Manually mapping month numbers to month names
        month_names = {
            1: "January", 2: "February", 3: "March", 4: "April",
            5: "May", 6: "June", 7: "July", 8: "August",
            9: "September", 10: "October", 11: "November", 12: "December"
        }

        best_month_name = month_names.get(best_month_number)
        best_month_request_count = best_month_data[1]  


        all_months_query = """
            SELECT MONTH(request_datetime) as month, COUNT(*) as request_count
            FROM Request
            WHERE userid = %s AND YEAR(request_datetime) = %s
            GROUP BY MONTH(request_datetime)
        """
        cursor.execute(all_months_query, (userid, year))
        all_months_data = cursor.fetchall()

  
        all_months_request_counts = {month: count for month, count in all_months_data}

        # Create response data
        response_data = {
            "best_month": best_month_name,
            "request_count": best_month_request_count,

        }

        return jsonify(response_data), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch data", "error": str(error)}), 500

@app.route('/user/get_info', methods=['GET'])
def get_user_info():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    try:
        query = "SELECT * FROM User WHERE username = %s"
        cursor.execute(query, (username,))
        user_info = cursor.fetchone()

        if not user_info:
            return jsonify({"message": "User not found"}), 404

        user_data = {
            
            "username": user_info[1],
            "email": user_info[2],
            "typeofplan": user_info[3],
            "request_count": user_info[5],
            # Include other user information columns here
        }

        return jsonify({"user_information": user_data}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch user information", "error": str(error)}), 500



@app.route('/user/all_requests', methods=['GET'])
def all_user_requests():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    query_check = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404

    userid = user[0]

    try:
        # Query to fetch all requests for the user
        all_requests_query = """
            SELECT * FROM Request
            WHERE userid = %s
        """
        cursor.execute(all_requests_query, (userid,))
        all_requests = cursor.fetchall()

        # Constructing the response with all user requests
        user_requests = []
        for row in all_requests:
            request_info = {
                "request_id": row[0],
                "camera_id": row[1],
                "camera_name": row[10],
                "license_type": row[3],
                "vechile_type":row[2],
                "request_datetime":str(row[9]),
                # Include other columns as needed
            }
            user_requests.append(request_info)

        return jsonify({"user_requests": user_requests}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch user requests", "error": str(error)}), 500

@app.route('/local-requests/all', methods=['GET'])
def all_user_local_requests():
    try:
       
        local_conn = sqlite3.connect('genuine_local.db')
        local_cursor = local_conn.cursor()

        all_requests_query = """
            SELECT * FROM Request
        """
        local_cursor.execute(all_requests_query)
        all_requests = local_cursor.fetchall()
        user_requests = []
        for row in all_requests:
            request_info = {
                "request_id": row[0],
                "camera_id": row[1],
                "camera_name": row[10],
                "license_type": row[3],
                "vechile_type": row[2],
                "request_datetime": str(row[9]),
                
            }
            user_requests.append(request_info)
        
        
        local_conn.close()

        return jsonify({"local_database": user_requests}), 200

    except sqlite3.Error as error:  # Catch sqlite3 errors
        return jsonify({"message": "Failed to fetch user requests", "error": str(error)}), 500
 #function to delete all records from local database   
def delete_records():
    try:
        # SQLite setup
        local_conn = sqlite3.connect('genuine_local.db', check_same_thread=False)
        local_cursor = local_conn.cursor()

        # Delete records
        local_cursor.execute('DELETE FROM Request')
        local_conn.commit()

    except Exception as e:
        print(f"Error in delete_records: {str(e)}")

    finally:
        # Close the database connection
        local_conn.close()

@app.route('/schedule_delete', methods=['POST'])
def schedule_delete():
    hours = request.json.get('hours', 24)  # Default to 24 hours if not provided

    # Remove all existing jobs
    scheduler.remove_all_jobs()

    # Schedule the delete_records function to run every N hours
    scheduler.add_job(delete_records, trigger=IntervalTrigger(hours=hours))

    return jsonify({"message": f"Scheduled deletion of all records every {hours} hours."})  
connected = False

#this is for the socketio(Background thread)
def background_thread():
    global ret,confidence
    global connected
    global registered
    while connected:
        license_dict={}
        threshold=confidence
        #LPR model init
        lpr_model_path = "./models/lpr+orientation.pt"
        model = YOLO(lpr_model_path)  

        cap = cv2.VideoCapture(camera_ip)
        while (cap.isOpened() and connected == True):
            # Capture frame-by-frame
            ret, img = cap.read()
            if not ret:
                break
            #detecting vehicles and classing them
            detected_vehicles=[]
            vehicle_id=''
            license_id=''
            direction=""
            detected_vehicles , vehicle_id =carAndPositionDetect(img,detected_vehicles)
            #cropping vehicles for LPR
            if detected_vehicles!=False:
                for veh in detected_vehicles:
                    x1 = int(veh[0])
                    y1 = int(veh[1])
                    x2 = int(veh[2])
                    y2 = int(veh[3])
                    cropped_vehicle = img[y1:y2, x1:x2]
                    results = model([cropped_vehicle])
                    for result in results:
                        boxes = result.boxes
                        names = result.names

                        if boxes ==False:
                            continue
                        #convert tensors to numpy arrays
                        boxes_np = boxes.xyxy.cpu().numpy()
                        classs_np = result.boxes.cls.cpu().numpy()
                        sorted_indices = np.argsort(boxes_np[:, 0])
                        sorted_classs = classs_np[sorted_indices]
                        #confidency
                        conf=result.boxes.conf
                        conf_np=conf.cpu().numpy()
                        conf_sum=conf_np.sum()
                        if conf_sum >0:
                            conf_sum=conf_sum/len(conf_np)

                        #vehicle_id crop
                        lid=0
                        sorted_boxes = boxes_np[boxes_np[:, 0].argsort()]
                        for index,clss in enumerate(sorted_classs):
                            if clss ==55:
                                lid=index
                            else:
                                license_id="GCC"

                        for num in sorted_classs:
                            if num ==56 or num==58:
                                direction="entering"
                            elif num ==57 or num==59:
                                direction="exiting"
                        if lid!=0:
                            #license id color detect
                            vehicle_id_img_bbox=sorted_boxes[lid]
                            x11 = int(vehicle_id_img_bbox[0])
                            y11 = int(vehicle_id_img_bbox[1])
                            x22 = int(vehicle_id_img_bbox[2])
                            y22 = int(vehicle_id_img_bbox[3])
                            vehicle_id_img= cropped_vehicle[y11:y22, x11:x22]
                            license_id=colorDetect(vehicle_id_img)

                        #sorting arabic and english license plate output 
                        arabic_plate=[]
                        english_plate=[]
                        for cls in sorted_classs.tolist():
                            if cls>=1 and cls<=27:
                                english_plate.append(cls)
                            elif cls>=28 and cls <=54:
                                arabic_plate.append(cls)
                        #final license format
                        arabic_translated_plate = license_formatting_ar(arabic_plate,names,vehicle_id)
                        english_processed_plate = license_formatting_en(english_plate,names)
                        if arabic_translated_plate!=False and english_processed_plate==False:
                            license_id = "old plate"
                        #applying optional threshold 
                        ret, buffer = cv2.imencode('.jpg', cropped_vehicle)
                        jpg_as_text = base64.b64encode(buffer)
                        if conf_sum>threshold:
                            print(f'the vehicle type is {vehicle_id}')
                            print(f'the license is of type {license_id}')
                            print(f'the license in arabic is = {arabic_translated_plate}')
                            print(f'the license in english is = {english_processed_plate}')
                            print(f'confidency is = {conf_sum}')
                            arabic_translated_plate = ', '.join(arabic_translated_plate)
                            english_processed_plate = ', '.join(english_processed_plate)

                            license_dict={
                                'vehicle_type':     vehicle_id,
                                'license_type':     license_id,
                                'plate_in_arabic':  arabic_translated_plate,                                                                                                                                    
                                'plate_in_english': english_processed_plate,
                                'confidence':       conf_sum,
                                'orientation' : direction,
                                'request_datetime' : datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'photo_data': jpg_as_text,
                                'userid' : userid,
                                'camera_name': camera_name,
                                'camera_id' : camera_id
                            }
                            license_dictWS={
                                'vehicle_type':     vehicle_id,
                                'license_type':     license_id,
                                'plate_in_arabic':  arabic_translated_plate,                                                                                                                                    
                                'plate_in_english': english_processed_plate,
                                'confidence':       conf_sum,
                                'orientation' : direction,
                                'request_datetime' : datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'userid' : userid,
                                'camera_name': camera_name,
                                'camera_id' : camera_id
                            }
                            socketio.emit('license', license_dictWS)
                            vehicle_query(license_dict)
                            time.sleep(7)
                        else:
                            continue
        cap.release()
        cv2.destroyAllWindows()

        
def vehicle_query(license_dict):
    sql = """
        INSERT INTO Request (
            userid,
            camera_id,
            camera_name,
            vehicle_type,
            license_type,
            plate_arabic,
            plate_english,
            confidence,
            orientation,
            photo_data,
            request_datetime
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
        """
    sqlite_sql = """
        INSERT INTO Request (
            user_id,
            camera_id,
            camera_name,
            vehicle_type,
            license_type,
            plate_arabic,
            plate_english,
            confidence,
            orientation,
            photo_data,
            request_datetime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)
        """

    cursor.execute(sql, (
            license_dict['userid'],
            license_dict['camera_id'],
            license_dict['camera_name'],
            license_dict['vehicle_type'],
            license_dict['license_type'],
            license_dict['plate_in_arabic'],
            license_dict['plate_in_english'],
            license_dict['confidence'],
            license_dict['orientation'],
            license_dict['photo_data'],
            license_dict['request_datetime'],
        ))
    local_cursor.execute(sqlite_sql, (
            license_dict['userid'],
            license_dict['camera_id'],
            license_dict['camera_name'],
            license_dict['vehicle_type'],
            license_dict['license_type'],
            license_dict['plate_in_arabic'],
            license_dict['plate_in_english'],
            license_dict['confidence'],
            license_dict['orientation'],
            license_dict['photo_data'],
            license_dict['request_datetime'],
        ))
    local_conn.commit()


        # Increment the request_count in the User table
    sql_update = """
        UPDATE User
        SET request_count = request_count + 1
        WHERE userid = %s
        """
    cursor.execute(sql_update, (userid,))

    conn.commit()


global camera_name, userid, camera_id
connected_cameras = {}
#this is for the socketio connection
@socketio.on('connect')
def handle_connect():
    global connected, userid, camera_id, camera_name, connected_cameras, camera_mode, confidence, camera_ip

    token = request.headers.get('X-My-Auth')
    camera_id = request.headers.get('X-Camera-Id')  # Get the camera id from the header

    if camera_id:
        connected_cameras[request.sid] = camera_id
    if token is not None and camera_id is not None:
        decoded_jwt = decode_access_token(token=token)
        if "message" in decoded_jwt:
            return jsonify(decoded_jwt)
        username = decoded_jwt["username"]
        query_check = "SELECT userid FROM User WHERE username = %s"
        cursor.execute(query_check, (username,))
        user = cursor.fetchone()
        cursor.fetchall()
   
        if not user:
            return jsonify({"message": "User does not exist"})
        
        # Get the camera name
        query_camera_name = "SELECT camera_name FROM Camera WHERE camera_id = %s"
        cursor.execute(query_camera_name, (camera_id,))
        camera = cursor.fetchone()
        cursor.fetchall()

        if not camera:
            return jsonify({"message": "Camera does not exist"})
        
        camera_name = camera[0]  # Store the camera name

        # Query the local database for the camera_mode, confidence_threshold, and camera_ip
        local_cursor.execute("SELECT camera_mode, confidence_threshold, camera_ip FROM Camera WHERE camera_id = ?", (camera_id,))
        result = local_cursor.fetchone()
        if result is not None:
            camera_mode, confidence, camera_ip = result

        print('Client connected, Camera ID:', camera_id, 'Camera Name:', camera_name)  # Print the camera id and name
        connected = True
        userid = user[0]  # Store the user id
        thread = threading.Thread(target=background_thread)
        thread.start()
    else:
        print('No token or camera id provided')

@socketio.on('disconnect')
def handle_disconnect():
    global connected, connected_cameras,camera_ip
    print('Client disconnected')
    connected = False

    # Remove the disconnected client from connected_cameras
    for socket_id, cam_id in list(connected_cameras.items()):  # Use list to avoid RuntimeError
        if request.sid == socket_id:
            del connected_cameras[socket_id]
            print('Removed Socket ID:', socket_id, 'from connected cameras')
            break





if __name__ == '__main__':
    scheduler.start()
    app.run(debug=True)
    socketio.run(app, debug=True)
