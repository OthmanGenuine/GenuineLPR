import cv2
from ultralytics import YOLO
import numpy as np
import server.support_methods as sp
from server.support_methods import license_formatting_ar,license_formatting_en,carAndPositionDetect,colorDetect
import base64
from flask_socketio import SocketIO, emit
from flask import Flask, request
import threading
#important variable dec
license_array=[]
license_dict={}
camera_array=[]
position=[]
threshold=0.2
#LPR model init
count=0
lpr_model_path = "./models/modelbeta0.0.2.pt"
model = YOLO(lpr_model_path)  

cap = cv2.VideoCapture('./testing_images/al.mp4')


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
                    license_dict={
                        'vehicle_type':     vehicle_id,
                        'license_type':     license_id,
                        'plate_in_arabic':  arabic_translated_plate,                                                                                                                                    
                        'plate_in_english': english_processed_plate,
                        'confidence':       conf_sum,
                        #'image': jpg_as_text,
                        #'orientation' : direction
                    }
                    print(license_dict)
                else:
                    continue
    cap.release()
    cv2.destroyAllWindows()
