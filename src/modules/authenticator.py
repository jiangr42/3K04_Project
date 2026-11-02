from modules.event_logger import EventLogger
from pathlib import Path
import yaml
import csv
import time
'''
PURPOSE

does authentication of users, supports multiple methods, which are each their own modules
authenticator gets called upon by other auth methods such as 
username password log in from GUI, and card reader module

Checks details against auth_details.csv, logs result and gives user level, and allowed meds

Also updates auth_detail.csv based on management system requests

Only checks credentials. Deciding if a user may log in to the current state is done by cabinet_controller
'''

FIELDNAMES = ["username", "password", "level", "last_login_attempt", "consecutive_failed_attempts", "allowed_medication"]
MEDICATION_SEPARATOR = ";" #allowed_medication is stored in one CSV cell, e.g. "advil;tylenol"
ALLOWED_CONSECUTIVE_FAILED_LOGINS = 3
LOCKOUT_PERIOD = 60 #lock out time in seconds

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

    def add_user(self, username, password, level, allowed_medication=()): #adds a user to the auth file. if success return 0
        #if sys error return 1, if user already exists return 2
        try:
            current_users = self._load_users()#load all users in a dict containing all associated info

            #determine if user already exists
            if (username in current_users):
                self.log.warning(f"user {username} already exists, cannot be added")
                return 2

            #add user into current users, then write it into CSV
            with open(self.auth_path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(
                    {"username": username, "password": password, "level": level, "last_login_attempt": 0, "consecutive_failed_attempts": 0,
                     "allowed_medication": MEDICATION_SEPARATOR.join(allowed_medication)}
                )
        except OSError as e:
            self.log.error(f"failed to add user {username}: {e}")
            return 1

        self.log.info(f"user {username} added with level {level}")
        return 0

    def delete_user(self, username): #removes a user from the auth file. if success return 0
        #if sys error return 1, if no user return 2
        try:
             #get list of all rows as dicts 
            with open(self.auth_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            #create new list of rows, except the row with the username give
            remaining = [row for row in rows if row["username"] != username]

            #if no change, then user is not found
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

        #allowed_medication is given as a list, convert it to the string stored in the CSV
        if "allowed_medication" in changes:
            changes["allowed_medication"] = MEDICATION_SEPARATOR.join(changes["allowed_medication"])

        try:
            #get list of all rows as dicts
            with open(self.auth_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            for row in rows:
                if row["username"] == username:
                    #if the right user, appply changes
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
        #external version for other modules, same as _load_users but without passwords
        users = self._load_users()
        for user in users.values():
            del user["password"]
        return users

    def _load_users(self):
        #internal version, includes passwords, only for use inside the authenticator
        users = {}
        with open(self.auth_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                users[row["username"]] = {
                    "level": row["level"],
                    "password": row["password"], 
                    "last_login_attempt": row["last_login_attempt"],
                    "consecutive_failed_attempts": row["consecutive_failed_attempts"],
                    "allowed_medication": row["allowed_medication"].split(MEDICATION_SEPARATOR) if row["allowed_medication"] else [],
                }
        return users
    
    def check_username_password(self, username, password): #given username, check if password is correct
        #also checks if log in is valid, if user is locked out return 3

        #returns a tuple, first int is status, 0 is success, 1 is failed, 2 is user not found, 3 is locked out.
        #second string user level
        #third is a list of allowed meds

        users = self._load_users()
        user = users.get(username)
        if user is None:
            self.log.warning(f"user {username} attempted log in, user not found")
            return (2, None, None)

        #get values about if the user is locked out
        failed_attempts = int(user["consecutive_failed_attempts"])
        time_since_last_attempt = time.time() - float(user["last_login_attempt"])

        #locked out if too many failed attempts and the lockout period hasn't passed yet
        if failed_attempts >= ALLOWED_CONSECUTIVE_FAILED_LOGINS:
            if time_since_last_attempt < LOCKOUT_PERIOD:
                remaining = int(LOCKOUT_PERIOD - time_since_last_attempt)
                self.log.warning(f"user {username} attempted log in, locked out for {remaining} more seconds")
                
                return (3, None, None)
            failed_attempts = 0 #lockout period is over, give the user a fresh set of attempts

        if user["password"] != str(password):
            #add one failed attempt
            failed_attempts += 1
            #update the last attempt time to now
            self.edit_user(username, consecutive_failed_attempts=failed_attempts, last_login_attempt=time.time())
            self.log.warning(f"user {username} attempted log in, password incorrect, failed attempts: {failed_attempts}")
            return (1, None, None)

        #successful log in, reset failed attempts
        self.edit_user(username, consecutive_failed_attempts=0, last_login_attempt=time.time())
        self.log.info(f"user {username} log in successful, user level: {user['level']}")
        return (0, user["level"], user["allowed_medication"])

    def check_username(self, username): #given username, check if it is correct
        #used for log in methods that "self authenticates" such as card or finger print

        #can log a user in even if they are password locked out

        #returns a tuple, first int is status, 0 is success, 2 is user not found
        #second string user level
        #third is a list of allowed meds

        users = self._load_users()
        user = users.get(username)
        if user is None:
            self.log.warning(f"user {username} attempted log in, user not found")
            return (2, None, None)

        #successful log in, reset failed attempts
        self.edit_user(username, consecutive_failed_attempts=0, last_login_attempt=time.time())
        self.log.info(f"user {username} log in successful, user level: {user['level']}")
        return (0, user["level"], user["allowed_medication"])