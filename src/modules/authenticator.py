from modules.event_logger import EventLogger
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

FIELDNAMES = ["username", "password", "level", "last_login_attempt", "consecutive_failed_attempts"]

class Authenticator:
    def __init__(self):
        #create logger
        self.log = EventLogger().logger

        #find auth file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        auth_config = self.config["authentication"]
        auth_details_dir = project_root / auth_config["auth_details"]["directory"]
        auth_details_dir.mkdir(parents=True, exist_ok=True)
        self.auth_path = auth_details_dir / auth_config["auth_details"]["filename"]

        self.init_auth_details_file()

    def init_auth_details_file(self):
        # create the file with a header row if it doesn't exist yet
        if not self.auth_path.exists():
            with open(self.auth_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
            self.log.info(f"created auth details file at {self.auth_path}")

    def add_user(self, username, password, level): #adds a user to the auth file. if success return 0
        #if sys error return 1, if user already exists return 2
        try:
            current_users = self.load_users()

            #determine if user already exists
            if (username in current_users):
                self.log.warning(f"user {username} already exists, cannot be added")
                return 2

            #add user into current users, then write it into CSV
            with open(self.auth_path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(
                    {"username": username, "password": password, "level": level, "last_login_attempt": 0, "consecutive_failed_attempts": 0}
                )
        except OSError as e:
            self.log.error(f"failed to add user {username}: {e}")
            return 1

        self.log.info(f"user {username} added with level {level}")
        return 0

    def delete_user(self, username): #removes a user from the auth file. if success return 0
        #if sys error return 1, if no user return 2
        try:
            #read every row, keeping all columns
            with open(self.auth_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            remaining = [row for row in rows if row["username"] != username]
            if len(remaining) == len(rows):
                self.log.warning(f"user {username} not found, cannot be deleted")
                return 2

            #rewrite the file without the deleted user
            with open(self.auth_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(remaining)
        except OSError as e:
            self.log.error(f"failed to delete user {username}: {e}")
            return 1

        self.log.info(f"user {username} deleted")
        return 0

    def edit_user(self, username, **changes): #edits fields of a user, example: edit_user("bob", password="new", level="user")
        #if success return 0, if sys error or invalid field return 1, if no user return 2

        #**changes is used because we might want to not change certain info
        invalid = [field for field in changes if field not in FIELDNAMES or field == "username"] #fields that are not allowed to be changed
        if invalid:
            self.log.error(f"cannot edit user {username}, invalid fields: {invalid}")
            return 1

        try:
            #read every row, keeping all columns
            with open(self.auth_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            for row in rows:
                if row["username"] == username:
                    row.update(changes)
                    break
            else:
                self.log.warning(f"user {username} not found, cannot be edited")
                return 2

            #rewrite the file with the edited row
            with open(self.auth_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as e:
            self.log.error(f"failed to edit user {username}: {e}")
            return 1

        self.log.info(f"user {username} edited, changed fields: {list(changes)}")
        return 0

    def load_users(self):
        users = {}
        with open(self.auth_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                users[row["username"]] = {
                    "level": row["level"],
                    "password": row["password"], 
                    "last_login_attempt": row["last_login_attempt"],
                    "consecutive_failed_attempts": row["consecutive_failed_attempts"]
                }
        return users

    def check_username_password(self, username, password): #given username, check if password is correct

        #returns a tuple, first int is status, 0 is success, 1 is failed, 2 is user not found. second string user level
        users = self.load_users()
        user = users.get(username)
        if user is None:
            self.log.warning(f"user {username} attempted log in, user not found")
            return (2, None)

        if user["Consecutive"]
        if user["password"] != str(password):
            self.log.warning(f"user {username} attempted log in, password incorrect, password is {password}")
            return (1, None)
        self.log.info(f"user {username} log in successful, user level: {user["level"]}")
        return (0, user["level"])
