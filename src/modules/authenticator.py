from event_logger import EventLogger
from pathlib import Path
import yaml
import csv
'''
PURPOSE

does authentication of users, supports multiple methods, which are each their own modules
authenticator gets called upon by other auth methods such as 
username password log in from GUI, and card reader module

Checks details against auth_details.csv, logs result and gives user level

Also updates auth_detail.csv based on management system requests
'''
class Authenticator:
    def __init__(self):
        #create logger
        self.log = EventLogger.logger

        #find auth file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        auth_config = self.config["authentication"]
        auth_details_dir = project_root / auth_config["auth_details"]["directory"]
        auth_details_dir.mkdir(parents=True, exist_ok=True)
        self.output_file_path = auth_details_dir / auth_config["auth_details"]["filename"]

    def load_users(self):
        users = {}
        with open(self.auth_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                users[row["username"]] = {
                    "level": row["level"],
                    "password": row["password"],
                }
        return users

    def check_username_password(self, username, password): #given username, check if password is correct

        #returns a tuple, first string status second string user level
        users = self.load_users()
        user = users.get(username)
        if user is None:
            self.log.warning(f"user {username} attempted log in, user not found")
            return ("USER_NOT_FOUND", None)
        if user["password"] != password:
            self.log.warning(f"user {username} attempted log in, password incorrect")
            return ("FAILED", None)
        self.log.warning(f"user {username} log in successful, user level: {user["level"]}")
        return ("SUCCESS", user["level"])
