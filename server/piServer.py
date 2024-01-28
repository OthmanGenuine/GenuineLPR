from flask import Flask, request, jsonify, abort
import mysql
import time
from mysql.connector.cursor_cext import CMySQLCursor
from datetime import datetime
from jose import JWTError, jwt
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
from mysql.connector import Error
import logging
app = Flask(__name__)
socketio = SocketIO(app)
scheduler = BackgroundScheduler(timezone="Asia/Riyadh")




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
        while True:
            try:
                conn.ping(reconnect=True)
                time_restored = time.time()
                print(f"Connection restored at {time_restored}")
                # If ping is successful, break the loop
                break
            except Error as e:
                time_lost = time.time()
                print(f"Connection lost at {time_lost}")
                # Wait for a while before trying to reconnect
                time.sleep(5)
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
                camera_id INTEGER,
                car_color VARCHAR(50),
                car_bodytype VARCHAR(50)
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



global camera_ip
SQLITE_DATABASE_FILE = 'genuine_local.db'

SECRET_KEY = "245"
ALGORITHM = "HS256"
def decode_access_token(*, token: str):
    try:
        decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_jwt
    except jwt.PyJWTError:
        return {"message": "Could not decode token"}



def create_sqlite_connection():
    return sqlite3.connect(SQLITE_DATABASE_FILE)


@app.route('/save_to_sqlite', methods=['POST'])
def save_to_sqlite():
    try:
   
        data_to_save = request.json

        # SQLite connection and cursor
        conn_local = create_sqlite_connection()
        local_cursor = conn_local.cursor()

        # Save data to SQLite
        query = "INSERT INTO Camera (camera_name, camera_mode, camera_ip,RaspareyPi_id ,confidence_threshold, camera_id) VALUES (?, ?, ?, ?, ?,?)"
        values = (
            data_to_save['camera_name'],
            data_to_save['camera_mode'],
            data_to_save['camera_ip'],
            data_to_save['RaspareyPi_id'],
            data_to_save['confidence_threshold'],
            data_to_save['camera_id']
        )
        local_cursor.execute(query, values)
        conn_local.commit()

        # Close the SQLite connection
        conn_local.close()

        return jsonify({'message': 'Data saved to SQLite successfully'})

    except Exception as e:
        logging.exception('An error occurred while processing the request.')
        return jsonify({'error': f'Failed to save data to SQLite: {str(e)}'}), 500
    



@app.route('/update_in_sqlite', methods=['PUT'])
def update_in_sqlite():
    try:
        #  data to be updated in the request
        data_to_update = request.json

        # SQLite connection and cursor
        conn = create_sqlite_connection()
        cursor = conn.cursor()

        # Update data in SQLite 
        query = "UPDATE Camera SET camera_name = ?, camera_mode = ?, confidence_threshold = ?, camera_ip = ? WHERE camera_id = ?"
        values = (
            data_to_update['camera_name'],
            data_to_update['camera_mode'],
            data_to_update['confidence_threshold'],
            data_to_update['camera_ip'],
            data_to_update['camera_id']
        )
        cursor.execute(query, values)
        conn.commit()

        # Close the SQLite connection
        conn.close()
        #logic to disconnect camera if its conncted to a socket
        if 'socketio' in globals():
            for socket_id, cam_id in connected_cameras.items():
                if cam_id == data_to_update['camera_id']:
                    print('Disconnecting Socket ID:', socket_id)
                    socketio.server.disconnect(socket_id)
                    confidence = data_to_update['confidence_threshold']
                    break

        return jsonify({'message': 'Data updated in SQLite successfully'})

    except Exception as e:
        return jsonify({'error': f'Failed to update data in SQLite: {str(e)}'}), 500
    
@app.route('/delete_in_sqlite', methods=['DELETE'])
def delete_in_pi():
    try:

        data_to_delete = request.json

        print('Received DELETE request with data:', data_to_delete)

        # SQLite connection and cursor
        conn = create_sqlite_connection()
        cursor = conn.cursor()

        #logic to disconnect camera if its conncted to a socket
        if 'socketio' in globals():
            for socket_id, cam_id in connected_cameras.items():
                if cam_id == data_to_delete['camera_id']:
                    print('Disconnecting Socket ID:', socket_id)
                    socketio.server.disconnect(socket_id)
                    break

        delete_query = "DELETE FROM Camera WHERE camera_id = ?"
        values = (data_to_delete['camera_id'],)
        cursor.execute(delete_query, values)

 
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'message': 'Camera not found in the database'}), 404


        conn.commit()
        conn.close()

        return jsonify({'message': 'Data deleted in pi successfully'})

    except Exception as e:
        print('Error:', str(e))
        return jsonify({'error': f'Failed to delete data in pi: {str(e)}'}), 500









 
connected = False

#this is for the socketio(Background thread)
def background_thread():
   
    global ret,confidence
    global connected
  
    while connected:
        license_dict={}
        threshold=confidence
        #LPR model init
        lpr_model_path = "./models/lpr+orientation.pt"
        model = YOLO(lpr_model_path)  
        from_localtemp_Table_to_cloud()
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
        
    while not connected:
        license_dict={}
        threshold=confidence
        #LPR model init
        lpr_model_path = "./models/lpr+orientation.pt"
        model = YOLO(lpr_model_path)  

        cap = cv2.VideoCapture(camera_ip)
        while (cap.isOpened() and connected == False):
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
                            offline_mode(license_dict)
                            socketio.emit('license', license_dictWS)
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
            request_datetime,
            car_color,
            car_bodytype

        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s,%s)
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
            car_color,
            car_bodytype

        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?,?,?)
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
            license_dict['car_color'],
            license_dict['car_bodytype'],

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
            license_dict['car_color'],
            license_dict['car_bodytype'],

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
def offline_mode(license_dict):
    create_temporary_table_sql = """
        CREATE TABLE IF NOT EXISTS request_temporary (
            user_id INTEGER,
            camera_id INTEGER,
            camera_name TEXT,
            vehicle_type TEXT,
            license_type TEXT,
            plate_arabic TEXT,
            plate_english TEXT,
            confidence REAL,
            orientation TEXT,
            photo_data BLOB,
            request_datetime TEXT,
            car_color TEXT,
            car_bodytype TEXT

        )
    """
    
    insert_request_sql = """
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
            car_color
            car_bodytype
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?,?)
    """
    
    insert_temporary_sql = """
        INSERT INTO request_temporary (
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
            request_datetime,
            car_color,
            car_bodytype
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?,?)
    """

    local_cursor.execute(create_temporary_table_sql)
    local_cursor.execute(insert_request_sql, (
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
        license_dict['car_color'],
        license_dict['car_bodytype'],
    ))
    
    local_cursor.execute(insert_temporary_sql, (
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
        license_dict['car_color'],
        license_dict['car_bodytype'],
    ))

    local_conn.commit()

def from_localtemp_Table_to_cloud():
    # Check if the request_temporary table exists
    local_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='request_temporary'")
    table_exists = local_cursor.fetchone()

    # If the table doesn't exist, break out of the function
    if not table_exists:
        print("The 'request_temporary' table doesn't exist. Exiting function.")
        return

    # Query data from the local request_temporary table
    local_cursor.execute("SELECT * FROM request_temporary")
    temporary_data = local_cursor.fetchall()

    # Insert data into the MySQL database's Request table
    for row in temporary_data:
        # Extract data from the row
        userid, camera_id, camera_name, vehicle_type, license_type, plate_arabic, plate_english, confidence, orientation, photo_data, request_datetime, car_color, car_bodytype = row

        # Insert data into the MySQL database's Request table
        mysql_sql = """
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
                car_color
                car_bodytype
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s)
        """
        cursor.execute(mysql_sql, (
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
            request_datetime,
            car_color,
            car_bodytype,
        ))

    # Commit changes to the MySQL database
    conn.commit()

    # Delete the temporary table from the local SQLite database
    local_cursor.execute("DROP TABLE IF EXISTS request_temporary")
    local_conn.commit()

#function for the delete records in sqlite database 
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
#endpoint for the schedule delete
@app.route('/schedule_delete', methods=['POST'])
def schedule_delete():
    hours = request.json.get('hours', 24)  # Default to 24 hours if not provided

    # Remove all existing jobs
    scheduler.remove_all_jobs()

    # Schedule the delete_records function to run every N hours
    scheduler.add_job(delete_records, trigger=IntervalTrigger(hours=hours))

    return jsonify({"message": f"Scheduled deletion of all records every {hours} hours."})  

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
    try:
        global connected, connected_cameras, camera_ip
        print('Client disconnected')
        connected = False

        # Remove the disconnected client from connected_cameras
        for socket_id, cam_id in list(connected_cameras.items()):  
            if request.sid == socket_id:
                del connected_cameras[socket_id]
                print('Removed Socket ID:', socket_id, 'from connected cameras')
                break
    except Exception as e:
        print('Error occurred during disconnection:', e)
  






if __name__ == "__main__":

    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
    scheduler.start()
    app.run(debug=True)
    app.run(allow_unsafe_werkzeug=True)