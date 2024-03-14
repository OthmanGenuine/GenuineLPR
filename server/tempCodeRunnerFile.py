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
                request_count INT DEFAULT 0

            )
            """,
            """
            CREATE TABLE IF NOT EXISTS Request (
                request_id INT AUTO_INCREMENT PRIMARY KEY,
                userid INT,
                camera_id INT,
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
                car_bodytype VARCHAR(50)

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
                camera_port INTEGER

            )
            """,
            """
            CREATE TABLE IF NOT EXISTS plan_types (
                plan_name VARCHAR(100) PRIMARY KEY,
                request_limit INT
                )
            """,
           

        ]
        alter_table_queries = [
    "ALTER TABLE User ADD CONSTRAINT fk_typeofplan FOREIGN KEY (typeofplan) REFERENCES plan_types(plan_name);",
    "ALTER TABLE Request ADD CONSTRAINT fk_userid FOREIGN KEY (userid) REFERENCES User(userid);",
    "ALTER TABLE Request ADD CONSTRAINT fk_cameraid FOREIGN KEY (camera_id) REFERENCES Camera(camera_id);",
    "ALTER TABLE Camera ADD CONSTRAINT fk_camera_userid FOREIGN KEY (userid) REFERENCES User(userid);"
]

    
        for query in queries:
            cursor.execute(query)
            conn.commit() 
        for query in alter_table_queries:
            cursor.execute(query)