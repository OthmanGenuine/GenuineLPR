import cv2
from ultralytics import YOLO
import numpy as np
vehicle_model=YOLO("./models/yolov8n.pt")


def license_formatting_en(english_plate,names):
    error="Error in detection or GCC plate"
    english_letter=[]
    english_num=[]
    english_processed_plate=[]
    #english formatting
    if len(english_plate)==4:
        english_num.append(english_plate[0])
        english_letter.append(english_plate[1])
        english_letter.append(english_plate[2])
        english_letter.append(english_plate[3])

    elif len(english_plate)==5:
        english_num.append(english_plate[0])
        english_num.append(english_plate[1])
        english_letter.append(english_plate[2])
        english_letter.append(english_plate[3])
        english_letter.append(english_plate[4])

    elif len(english_plate)==6:
        english_num.append(english_plate[0])
        english_num.append(english_plate[1])
        english_num.append(english_plate[2])
        english_letter.append(english_plate[3])
        english_letter.append(english_plate[4])
        english_letter.append(english_plate[5])

    elif len(english_plate)==7:
        english_num.append(english_plate[0])
        english_num.append(english_plate[1])
        english_num.append(english_plate[2])
        english_num.append(english_plate[3])
        english_letter.append(english_plate[4])
        english_letter.append(english_plate[5])
        english_letter.append(english_plate[6])
    else:
        english_processed_plate.append(error)
    if len(english_plate)>2:
        for number in english_num:
            english_processed_plate.append(names[number])
        for letter in english_letter:
            english_processed_plate.append(names[letter])
    #returning the relevant information
    return english_processed_plate

def license_formatting_ar(arabic_plate,names,vehicle_id):
    arabic_translated_plate=[]
    error="Error in detection or GCC plate"
    arabic_num=[]
    arabic_letter=[]
    arabic_processed_plate=[]
    #arabic formatting
    if len(arabic_plate)==4:
        arabic_num.append(arabic_plate[0])
        arabic_letter.append(arabic_plate[1])
        arabic_letter.append(arabic_plate[2])
        arabic_letter.append(arabic_plate[3])
    
    elif len(arabic_plate)==4 and vehicle_id =='motorbike':
        arabic_num.append(arabic_plate[0])
        arabic_num.append(arabic_plate[1])
        arabic_letter.append(arabic_plate[2])
        arabic_letter.append(arabic_plate[3])

    elif len(arabic_plate)==5 and vehicle_id =='motorbike':
        arabic_num.append(arabic_plate[0])
        arabic_num.append(arabic_plate[1])
        arabic_num.append(arabic_plate[2])
        arabic_letter.append(arabic_plate[3])
        arabic_letter.append(arabic_plate[4])

    elif len(arabic_plate)==5:
        arabic_num.append(arabic_plate[0])
        arabic_num.append(arabic_plate[1])
        arabic_letter.append(arabic_plate[2])
        arabic_letter.append(arabic_plate[3])
        arabic_letter.append(arabic_plate[4])

    elif len(arabic_plate)==6:
        arabic_num.append(arabic_plate[0])
        arabic_num.append(arabic_plate[1])
        arabic_num.append(arabic_plate[2])
        arabic_letter.append(arabic_plate[3])
        arabic_letter.append(arabic_plate[4])
        arabic_letter.append(arabic_plate[5])

    elif len(arabic_plate)==7:
        arabic_num.append(arabic_plate[0])
        arabic_num.append(arabic_plate[1])
        arabic_num.append(arabic_plate[2])
        arabic_num.append(arabic_plate[3])
        arabic_letter.append(arabic_plate[4])
        arabic_letter.append(arabic_plate[5])
        arabic_letter.append(arabic_plate[6])
    else:
        arabic_translated_plate.append(error)
    if len(arabic_plate)>2:
        for number in arabic_num:
            arabic_processed_plate.append(number)
        for letter in arabic_letter:
            arabic_processed_plate.append(letter)


    #normalization
    # Define the English to Arabic translation dictionary
    translation_dict = {
        28: 'ا',
        29: 'ب',
        30: 'ح', 
        31: 'د',
        32: 'ر',
        33: 'س',
        34: 'ص',
        35: 'ط',
        36: 'ع',
        37: 'ق',
        38: 'ك',
        39: 'ل',
        40: 'م',
        41: 'ن',
        42: 'ه',
        43: 'و',
        44: 'ى', 
        45: '٠',
        46: '١',
        47: '٢',
        48: '٣',
        49: '٤',
        50: '٥',
        51: '٦',
        52: '٧',
        53: '٨',
        54: '٩'}
    # Translate the English string to Arabic using the translation dictionary
    if arabic_processed_plate!= False:
        for ch in arabic_processed_plate:
            arabic_translated_plate.append(translation_dict[ch])
    #returning the relevant information
    return arabic_translated_plate

def carAndPositionDetect(img,detected_vehicles):
    vehicle_id=""
    desired_classes=[2,3,5,7]
    vehicles = vehicle_model(img)[0]
    for vehicle in vehicles.boxes.data.tolist():
        x1, y1, x2, y2, confidence_score, class_id = vehicle
        if class_id in desired_classes:
            if class_id==3:
                vehicle_id='motorbike'
            elif class_id==2:
                vehicle_id='car'
            elif class_id==5:
                vehicle_id='bus'
            elif class_id==7:
                vehicle_id='truck'
            else:
                vehicle_id='no vehicle detected'
            detected_vehicles.append((x1, y1, x2, y2, class_id))
    return detected_vehicles , vehicle_id

def colorDetect(vehicle_id_img):
    hsv = cv2.cvtColor(vehicle_id_img, cv2.COLOR_BGR2HSV)
    lower_green = np.array([40, 50, 50])
    upper_green = np.array([80, 255, 255])

    lower_yellow = np.array([15, 50, 50])
    upper_yellow = np.array([40, 255, 255])

    lower_blue = np.array([90, 50, 50])
    upper_blue = np.array([130, 255, 255])

    # Mask for each color
    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

    # Bitwise AND to extract the regions of interest
    res_green = cv2.bitwise_and(vehicle_id_img, vehicle_id_img, mask=mask_green)
    res_yellow = cv2.bitwise_and(vehicle_id_img, vehicle_id_img, mask=mask_yellow)
    res_blue = cv2.bitwise_and(vehicle_id_img, vehicle_id_img, mask=mask_blue)

    # Check for presence of each color
    if cv2.countNonZero(mask_yellow) > 1000:
        license_id="Taxi"
    elif cv2.countNonZero(mask_green) > 1000:
        license_id="Diplomatic"
    elif cv2.countNonZero(mask_blue) > 1000:
        license_id="Commercial"
    else:
        license_id= "private"
    return license_id