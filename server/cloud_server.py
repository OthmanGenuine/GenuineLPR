from flask import Flask, request, jsonify, abort
import mysql
import time
from mysql.connector.cursor_cext import CMySQLCursor
from pydantic import BaseModel, ValidationError,EmailStr, Field,confloat
from passlib.hash import pbkdf2_sha256
from datetime import datetime
from jose import JWTError, jwt
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
import requests


# Create a Flask application instance
app = Flask(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Riyadh")




#this is for connecting to the database with  project enter your database information here
mysql_success = False


while not (mysql_success):
    try:
        # enter cloud server cred (mysql)
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
                request_count INT DEFAULT 0,
                FOREIGN KEY (typeofplan) REFERENCES plan_types(plan_name)
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
                car_color VARCHAR(50),
                car_bodytype VARCHAR(50),
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
                camera_port INTEGER,
                FOREIGN KEY (userid) REFERENCES User(userid)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS plan_types (
                plan_name VARCHAR(100) PRIMARY KEY,
                request_limit INT
                )
            """,
        ]

  
        for query in queries:
            cursor.execute(query)

        print("MySQL Database connection and table creation successful!")
      
        mysql_success = True








    except mysql.connector.Error as mysql_error:
        print("MySQL Connection or setup failed")
        print("MySQL Error:", mysql_error)


    time.sleep(5)  # Wait 5 seconds before attempting MySQL and SQLite setup again

# Both databases connected successfully, break out of the loop


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
    RaspareyPi_id :str
    camera_port :int
    confidence_threshold: confloat(strict=True, lt=1.0)

class CameraIdBaseModel(BaseModel):
    camera_id: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=50,
      )


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
    
    
@app.route('/user/update_plan', methods=['PUT'])
def update_plan():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    try:
        new_plan = request.json.get('new_plan')

        # Update the type of plan for the authenticated user
        update_query = "UPDATE User SET typeofplan = %s WHERE username = %s"
        cursor.execute(update_query, (new_plan, decoded_jwt['username']))
        conn.commit()

        return jsonify({"message": "Type of plan updated successfully"}), 200

    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to update type of plan", "error": str(error)}), 500
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

sqlite_camerasave_url = 'https://bef979b1e6489c.lhr.life/save_to_sqlite'

@app.route('/user/camera/add', methods=['POST'])
def add_camera():
    global camera_id, camera_ip, confidence

    try:
        camera_data = CameraData(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

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

    query = "INSERT INTO Camera (camera_name, camera_mode, camera_ip, raspberrypi_id,confidence_threshold,camera_port ,userid) VALUES (%s, %s, %s, %s, %s,%s,%s)"

    values = (camera_data.camera_name, camera_data.camera_mode, camera_data.camera_ip,camera_data.RaspareyPi_id,camera_data.confidence_threshold,camera_data.camera_port ,userid)

    try:
        cursor.execute(query, values)
        conn.commit()

        camera_id = cursor.lastrowid  # Update the global variable with the last inserted camera_id

        # Insert the same data into the other endpoint
        
        request_json_with_id = request.json.copy()
        request_json_with_id["camera_id"] = camera_id
        response = requests.post(sqlite_camerasave_url, json=request_json_with_id)
        if response.status_code != 200:
            return jsonify({"message": "Failed to save data to the other endpoint"}), 500
          
        return jsonify({"message": "Camera added successfully", "camera_id": camera_id})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to add camera", "error": str(error)}), 500
#this endpoint for the user camera update
sqlite_update_camera_url= 'https://bef979b1e6489c.lhr.life/update_in_sqlite'
@app.route('/user/camera/update', methods=['PUT'])  
def update_camera():
    global connected_cameras, confidence

    try:
        # Validate and parse the incoming JSON data
        camera_data = CameraData(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)})

    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"})

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt)

    username = decoded_jwt["username"]

    # Check if the user exists
    query_check_user = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check_user, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"})

    userid = user[0]

    # Check if the camera exists and belongs to the user
    query_check_camera = "SELECT * FROM Camera WHERE camera_id = %s AND userid = %s"
    cursor.execute(query_check_camera, (camera_data.camera_id, userid))
    camera = cursor.fetchone()
    if not camera:
        return jsonify({"message": "Camera not found or does not belong to the user"})

    camera_id_to_update = camera_data.camera_id

    # Update the camera in the MySQL database
    query_update_mysql = "UPDATE Camera SET camera_name = %s, camera_mode = %s, confidence_threshold = %s, camera_ip = %s,raspberrypi_id= %s, camera_port= %s  WHERE camera_id = %s"
    values_update_mysql = (
        camera_data.camera_name,
        camera_data.camera_mode,
        camera_data.confidence_threshold,
        camera_data.camera_ip,
        camera_data.RaspareyPi_id,
        camera_data.camera_port,
        camera_id_to_update
    )

    # Update the camera in the SQLite database through another endpoint
    try:
        cursor.execute(query_update_mysql, values_update_mysql)
        conn.commit()

        # Send update request to the other endpoint for SQLite update
       
        response = requests.put(sqlite_update_camera_url, json=request.json)

        if response.status_code != 200:
            return jsonify({"message": "Failed to update data in SQLite"}), 500
       
        # Additional logic for handling connected cameras, etc.

        return jsonify({"message": "Camera updated successfully"})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to update camera in MySQL", "error": str(error)}), 500

sqlite_delete_endpoint_url = 'https://9978eaf1b70fe2.lhr.life/delete_in_sqlite'
   
#this endpoint for the user camera delete
@app.route('/user/camera/delete', methods=['DELETE'])
def delete_camera():
    global connected_cameras

    try:
        # Validate and parse the incoming JSON data
        camera_data = CameraIdBaseModel(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)}), 400
    except JWTError as e:
        # Check if the specific error is related to the missing attribute
        if "PyJWTError" in str(e):
            return jsonify({"message": "Token error (PyJWTError)", "error": str(e)})
        else:
            return jsonify({"message": "JWT error", "error": str(e)})

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt), 401

    username = decoded_jwt["username"]

    # Check if the user exists
    query_check_user = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check_user, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404
    
    userid = user[0]

    # Extract camera_id to delete
    camera_id_to_delete = camera_data.camera_id

    if not camera_id_to_delete:
        return jsonify({"message": "Missing camera_id in the request"}), 400

    # Check if the camera exists and belongs to the user
    query_check_camera = "SELECT camera_id FROM Camera WHERE camera_id = %s AND userid = %s"
    cursor.execute(query_check_camera, (camera_id_to_delete, userid,))
    camera = cursor.fetchone()

    if not camera:
        return jsonify({"message": "Camera does not exist or does not belong to the user"}), 404

    try:
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        # Now, delete the camera
        delete_query = "DELETE FROM Camera WHERE camera_id = %s"
        cursor.execute(delete_query, (camera_id_to_delete,))
        conn.commit()

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")

        # Send delete request to the other endpoint for disconnecting socket
        """ 
        print("Before DELETE request")
        response = requests.delete(sqlite_delete_endpoint_url, json=request.json)
        print("After DELETE request")
        print(response.status_code)

        if response.status_code != 200:
            return jsonify({"message": "Failed to delete camera in the other endpoint"}), 500
        """ 
        return jsonify({"message": "Camera deleted successfully"}), 200
    

    except mysql.connector.Error as error:
        conn.rollback()
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        return jsonify({"message": "Failed to delete camera", "error": str(error)}), 500

@app.route('/user/cameras/get', methods=['GET'])
def get_cameras():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    try:
        decoded_jwt = decode_access_token(token=token)
    except Exception as e:
        return jsonify({"message": "Invalid token", "error": str(e)}), 401

    username = decoded_jwt["username"]

    # Check if the user exists
    query_check_user = "SELECT userid FROM User WHERE username = %s"
    cursor.execute(query_check_user, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404

    userid = user[0]

    # Get all cameras related to the user
    query_get_cameras = "SELECT * FROM Camera WHERE userid = %s"
    cursor.execute(query_get_cameras, (userid,))
    cameras = cursor.fetchall()

    if not cameras:
        return jsonify({"message": "No cameras found for the user"}), 404

    # Convert the result to JSON
    cameras_json = [dict(zip([key[0] for key in cursor.description], row)) for row in cameras]

    return jsonify({"message": "Cameras fetched successfully", "cameras": cameras_json}), 200    
@app.route('/user/change_password', methods=['PUT'])
def change_password():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"}), 401

    token = auth_header.split(" ")[1]
    try:
        decoded_jwt = decode_access_token(token=token)
    except Exception as e:
        return jsonify({"message": "Invalid token", "error": str(e)}), 401

    username = decoded_jwt["username"]

    # Check if the user exists
    query_check_user = "SELECT userid, password FROM User WHERE username = %s"
    cursor.execute(query_check_user, (username,))
    user = cursor.fetchone()
    if not user:
        return jsonify({"message": "User does not exist"}), 404

    userid, hashed_password = user

    # Validate and parse the incoming JSON data
    try:
        password_data = ChangePasswordRequest(**request.json)
    except ValidationError as e:
        return jsonify({"message": "Validation error", "error": str(e)}), 400

    # Check if the old password is correct
    if not pbkdf2_sha256.verify(password_data.old_password, hashed_password):
        return jsonify({"message": "Old password is incorrect"}), 401

    # Update the password
    new_hashed_password = pbkdf2_sha256.hash(password_data.new_password)

    update_query = "UPDATE User SET password = %s WHERE userid = %s"
    cursor.execute(update_query, (new_hashed_password, userid))
    conn.commit()

    return jsonify({"message": "Password updated successfully"}), 200

@app.route('/user/camera/getAllCameraRequestCounts', methods=['GET'])
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
    

@app.route('/user/requests_in_day_hour', methods=['POST'])
def requests_in_day_hour():
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

    # Fetching the date and hour from the request body
    data = request.json
    date = data.get('date')
    hour = data.get('hour')

    try:
        # Parse date and hour strings to datetime objects
        date_dt = datetime.strptime(date, '%Y-%m-%d')
        hour_dt = datetime.strptime(hour, '%I%p').strftime('%H')

        # Fetch requests that occurred during the specified date and hour
        requests_query = """
            SELECT COUNT(*) FROM Request 
            WHERE userid = %s 
            AND DATE(request_datetime) = %s
            AND HOUR(request_datetime) = %s
        """
        cursor.execute(requests_query, (userid, date_dt, hour_dt))
        num_requests = cursor.fetchone()[0]

        return jsonify({"number of vehicles entered": num_requests}), 200

    except mysql.connector.Error as error:
        return jsonify({"message": "Failed to fetch requests in the day and hour", "error": str(error)}), 500



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
    
#here we need it to make a request to the pi server to get all the data in the pi server 
#database we need to make another endpoint in the pi server to hanedl this
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

from flask import jsonify, request

@app.route('/statistics/car_bodytype_percentage', methods=['GET'])
def car_bodytype_percentage():
    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return jsonify({"message": "Authorization header is missing"})

    token = auth_header.split(" ")[1]
    decoded_jwt = decode_access_token(token=token)
    if "message" in decoded_jwt:
        return jsonify(decoded_jwt)

    username = decoded_jwt["username"]

    try:
        # Get the user ID from the decoded token
        query_user_id = "SELECT userid FROM User WHERE username = %s"
        cursor.execute(query_user_id, (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"message": "User does not exist"})

        userid = user[0]

        # Count the total number of cars for the user
        total_count_query = "SELECT COUNT(*) FROM request WHERE userid = %s"
        cursor.execute(total_count_query, (userid,))
        total_count = cursor.fetchone()[0]

        if total_count == 0:
            return jsonify({"message": "No cars in the database for the user"})

        # Get the distribution of car_bodytype for the user
        bodytype_distribution_query = "SELECT car_bodytype, COUNT(*) as count FROM request WHERE userid = %s GROUP BY car_bodytype"
        cursor.execute(bodytype_distribution_query, (userid,))
        bodytype_distribution = cursor.fetchall()

        percentage_distribution = []
        for bodytype, count in bodytype_distribution:
            percentage = (count / total_count) * 100
            percentage_distribution.append({"car_bodytype": bodytype, "percentage": percentage})

        return jsonify({"percentage_distribution": percentage_distribution})
    except Exception as e:
        return jsonify({"message": "Error retrieving data", "error": str(e)})
from flask import jsonify, request
from jose.exceptions import JWTError, ExpiredSignatureError

@app.route('/statistics/car_color_distribution', methods=['GET'])
def car_color_distribution():
    try:
        auth_header = request.headers.get('Authorization', None)
        if not auth_header:
            return jsonify({"message": "Authorization header is missing"})

        token = auth_header.split(" ")[1]
        decoded_jwt = decode_access_token(token=token)
        if "message" in decoded_jwt:
            return jsonify(decoded_jwt)

        username = decoded_jwt["username"]

        # Get the user ID from the decoded token
        query_user_id = "SELECT userid FROM User WHERE username = %s"
        cursor.execute(query_user_id, (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"message": "User does not exist"})

        userid = user[0]

        # Get the distribution of car colors for the user
        color_distribution_query = "SELECT car_color, COUNT(*) as count FROM request WHERE userid = %s GROUP BY car_color"
        cursor.execute(color_distribution_query, (userid,))
        color_distribution = cursor.fetchall()

        total_count_query = "SELECT COUNT(*) FROM request WHERE userid = %s"
        cursor.execute(total_count_query, (userid,))
        total_count = cursor.fetchone()[0]

        if total_count == 0:
            return jsonify({"message": "No cars in the database for the user"})

        percentage_distribution = []
        for color, count in color_distribution:
            percentage = (count / total_count) * 100
            percentage_distribution.append({"car_color": color, "percentage": percentage})

        return jsonify({"color_distribution": percentage_distribution})



    except JWTError as e:
        # Check if the specific error is related to the missing attribute
        if "PyJWTError" in str(e):
            return jsonify({"message": "Token error (PyJWTError)", "error": str(e)})
        else:
            return jsonify({"message": "JWT error", "error": str(e)})

    except Exception as e:
        return jsonify({"message": "Error retrieving data", "error": str(e)})
@app.route('/statistics/bodytype_color_combinations', methods=['GET'])
def bodytype_color_combinations():
    try:
        auth_header = request.headers.get('Authorization', None)
        if not auth_header:
            return jsonify({"message": "Authorization header is missing"})

        token = auth_header.split(" ")[1]
        decoded_jwt = decode_access_token(token=token)
        if "message" in decoded_jwt:
            return jsonify(decoded_jwt)

        username = decoded_jwt["username"]

        # Get the user ID from the decoded token
        query_user_id = "SELECT userid FROM User WHERE username = %s"
        cursor.execute(query_user_id, (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"message": "User does not exist"})

        userid = user[0]

        # Get the top N combinations of car_bodytype and car_color for the user
        top_combinations_query = """
            SELECT car_bodytype, car_color, COUNT(*) as count
            FROM request
            WHERE userid = %s
            GROUP BY car_bodytype, car_color
            ORDER BY count DESC
            LIMIT 10
        """
        cursor.execute(top_combinations_query, (userid,))
        top_combinations = cursor.fetchall()

        total_count_query = "SELECT COUNT(*) FROM request WHERE userid = %s"
        cursor.execute(total_count_query, (userid,))
        total_count = cursor.fetchone()[0]

        if total_count == 0:
            return jsonify({"message": "No cars in the database for the user"})

        combination_distribution = []
        for rank, (bodytype, color, count) in enumerate(top_combinations, start=1):
            percentage = (count / total_count) * 100
            combination_distribution.append({
                "rank": rank,
                "car_bodytype": bodytype,
                "car_color": color,
                "percentage": percentage
            })

        return jsonify({"top_bodytype_color_combinations": combination_distribution})



    except JWTError as e:
        # Check if the specific error is related to the missing attribute
        if "PyJWTError" in str(e):
            return jsonify({"message": "Token error (PyJWTError)", "error": str(e)})
        else:
            return jsonify({"message": "JWT error", "error": str(e)})

    except Exception as e:
        return jsonify({"message": "Error retrieving data", "error": str(e)})
if __name__ == '__main__':
    scheduler.start()
    app.run(debug=True)

