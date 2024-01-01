from flask import Flask, request, jsonify, abort
from flask_swagger_ui import get_swaggerui_blueprint
import mysql
import time
from mysql.connector.cursor_cext import CMySQLCursor
from pydantic import BaseModel, ValidationError,EmailStr, Field
from passlib.hash import pbkdf2_sha256
from datetime import datetime
from jose import JWTError, jwt
import secrets
from typing import Optional
import json
from flask_socketio import SocketIO, emit
import threading
import base64
from ultralytics import YOLO
from support_methods import license_formatting_ar,license_formatting_en,carAndPositionDetect,colorDetect
import cv2
import numpy as np
app = Flask(__name__)
socketio = SocketIO(app)


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
while True:
    try:
        conn = mysql.connector.connect(
                    host='localhost',
                    database='testDB',
                    user='root',
                    password='Uu12345-'
                )

        cursor = conn.cursor(cursor_class=CMySQLCursor, buffered=True)


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
                FOREIGN KEY (userid) REFERENCES User(userid)
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
                FOREIGN KEY (userid) REFERENCES User(userid)
            )
            """,
        ]

        for query in queries:
            cursor.execute(query)

        print("Database connection was successful!")
        break
    except mysql.connector.Error as error:
        print("Connecting to the database failed")
        print("Error:", error)
        time.sleep(2)

#this is for the validation schema for the user

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


# this endpoint for the user camera add
@app.route('/user/camera/add', methods=['POST'])
def add_camera():
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

    query = "INSERT INTO Camera (camera_name, camera_mode, camera_ip, userid) VALUES (%s, %s, %s, %s)"
    values = (camera_data.camera_name, camera_data.camera_mode, camera_data.camera_ip, userid)

    try:
        cursor.execute(query, values)
        conn.commit()

       
        camera_id = cursor.lastrowid

        return jsonify({"message": "Camera added successfully", "camera_id": camera_id})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to add camera", "error": str(error)})
#this endpoint for the user camera update
@app.route('/user/camera/update', methods=['PUT'])
def update_camera():
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

  
    query_check = "SELECT * FROM Camera WHERE camera_id = %s AND userid = %s"
    cursor.execute(query_check, (camera_data.camera_id, userid))
    camera = cursor.fetchone()
    if not camera:
        return jsonify({"message": "Camera not found or does not belong to the user"})

    query = "UPDATE Camera SET camera_name = %s, camera_mode = %s, camera_ip = %s WHERE camera_id = %s"
    values = (camera_data.camera_name, camera_data.camera_mode, camera_data.camera_ip, camera_data.camera_id)

    try:
        cursor.execute(query, values)
        conn.commit()
        return jsonify({"message": "Camera updated successfully"})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to update camera", "error": str(error)})
    
#this endpoint for the user camera delete
@app.route('/user/camera/delete', methods=['DELETE'])
def delete_camera():
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

    
    data = request.json
    camera_id_to_delete = data.get('camera_id')

    if not camera_id_to_delete:
        return jsonify({"message": "Missing camera_id in the request"})

    try:
        
        query_check = "SELECT * FROM Camera WHERE camera_id = %s AND userid = %s"
        cursor.execute(query_check, (camera_id_to_delete, userid))
        camera = cursor.fetchone()

        if not camera:
            return jsonify({"message": "Camera not found or does not belong to the user"})

        
        delete_query = "DELETE FROM Camera WHERE camera_id = %s"
        cursor.execute(delete_query, (camera_id_to_delete,))
        conn.commit()
        return jsonify({"message": "Camera deleted successfully"})
    except mysql.connector.Error as error:
        conn.rollback()
        return jsonify({"message": "Failed to delete camera", "error": str(error)})
    

connected = False
#this is for the socketio(Background thread)
def background_thread():
    global connected
    while connected:
        license_dict={}
        threshold=0.2
        #LPR model init
        lpr_model_path = "./models/lpr+orientation.pt"
        model = YOLO(lpr_model_path)  

        cap = cv2.VideoCapture('testing_images/al.mp4')
        while (cap.isOpened()):
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
                                'photo_data': jpg_as_text
                            }
                            print(license_dict)
                            socketio.emit('license', license_dict)
                            vehicle_query(license_dict)
                            time.sleep(1)
                        else:
                            continue
        cap.release()
        cv2.destroyAllWindows()

        
def vehicle_query(license_dict):
    sql = """
    INSERT INTO Request (
        vehicle_type,
        license_type,
        plate_arabic,
        plate_english,
        confidence,
        orientation,
        request_datetime,
        photo_data
    ) VALUES (%s, %s, %s, %s, %s,%s,%s,%s)
    """

    cursor.execute(sql, (
        license_dict['vehicle_type'],
        license_dict['license_type'],
        license_dict['plate_in_arabic'],
        license_dict['plate_in_english'],
        license_dict['confidence'],
        license_dict['orientation'],
        license_dict['request_datetime'],
        license_dict['photo_data'],
    ))

    conn.commit()



#this is for the socketio connection
@socketio.on('connect')
def handle_connect():
    global connected
    print('Client connected')
    connected = True
    thread = threading.Thread(target=background_thread)
    thread.start()
#this is for the socketio disconnection
@socketio.on('disconnect')
def handle_disconnect():
    global connected
    print('Client disconnected')
    connected = False

if __name__ == '__main__':
    app.run(debug=True)
    socketio.run(app, debug=True)
