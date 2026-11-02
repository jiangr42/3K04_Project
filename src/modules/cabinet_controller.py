from modules.event_logger import EventLogger
from modules.authenticator import Authenticator
#from modules.inventory_tracker import InventoryTracker
from pathlib import Path
import yaml
import csv
import time

DEFAULT_ID = "000"

ALL_STATES = ["Standby", "Dispensing", "Restocking", "Maintenance", "Locked", "EmergencyShutdown", "Fault"]

#current states each user level is allowed to log in during
LOGIN_ALLOWED_IN = {
    "Admin": ALL_STATES,
    "Maintenance": ["Standby", "Maintenance", "Fault", "EmergencyShutdown"],
    "Nurse": ["Standby"],
}

#states each logged in user level is allowed to switch the cabinet into, for use by the state change logic
CAN_ENTER = {
    "Admin": ["Standby", "Maintenance", "Locked", "EmergencyShutdown", "Fault"], #admin cannot access meds
    "Maintenance": ["Maintenance"],
    "Nurse": ["Dispensing", "Restocking"],
}

class Cabinet_Controller:
    def __init__(self):
        ################################
        # state variables
        ################################
        self.ID = DEFAULT_ID
        self.state = "Standby" #can be Dispensing, Restocking
        #Maintenance, Locked, EmergencyShutdown, or Fault state

        self.current_username = None #string for username, None if no one is logged in
        self.current_user_level = None #string for level, either Admin, Maintenance, or Nurse
        self.current_user_allowed_medication = None #list of string of allowed meds

        ###############################
        # object instaciation
        ###############################

        #create logger
        self.log = EventLogger().logger

        self.authenticator = Authenticator()
        #self.inventory_tracker = InventoryTracker()

        #need to add more stuff

    ################################
    #LOGIN/OUT
    ################################

    def username_password_login(self, username, password):
        #logs in a user, called by the GUI when it gets a log in request
        #only decides if the user can log in during the current state, does not change state

        #returns status int: 0 success, 1 password incorrect, 2 user not found, 3 user locked out (same as authenticator),
        #4 not allowed to log in during current state, 5 another user is logged in

        #checked before the authenticator so a rejected log in doesn't count as a failed attempt
        if self.current_username is not None:
            self.log.warning(f"user {username} attempted log in, user {self.current_username} is already logged in")
            return 5

        status, level, allowed_medication = self.authenticator.check_username_password(username, password)
        return self._complete_login(username, status, level, allowed_medication)

    def username_login(self, username):
        #logs in a user, called by the card reader when it gets a log in request
        #no password needed, having the card is the proof of identity
        #only decides if the user can log in during the current state, does not change state

        #returns status int: 0 success, 2 user not found (same as authenticator),
        #4 not allowed to log in during current state, 5 another user is logged in
        if self.current_username is not None:
            self.log.warning(f"user {username} attempted log in, user {self.current_username} is already logged in")
            return 5

        status, level, allowed_medication = self.authenticator.check_username(username)
        return self._complete_login(username, status, level, allowed_medication)

    def _complete_login(self, username, status, level, allowed_medication):
        #takes the result of the authenticator check
        #returns the authenticator status if it failed, 4 if not allowed to log in during current state, 0 on success
        if status != 0:
            return status

        #role check is done after the credential check so it doesn't reveal anything to someone without valid credentials
        if self.state not in LOGIN_ALLOWED_IN.get(level, []):
            self.log.warning(f"user {username} with level {level} not allowed to log in during state {self.state}")
            return 4

        #update vars when log in successful
        self.current_username = username
        self.current_user_level = level
        self.current_user_allowed_medication = allowed_medication
        self.log.info(f"user {username} logged in, level {level}, state {self.state}")
        return 0

    def logout(self):
        #logs out the current user and returns the cabinet to Standby
        #Fault and EmergencyShutdown also go back to Standby, if the problem is still there the controller will detect it again
        #Locked stays Locked, so an admin logging in and out doesn't unlock the cabinet

        #returns status int: 0 success, 1 no user logged in
        if self.current_username is None:
            self.log.warning("log out requested, no user is logged in")
            return 1

        if self.state != "Locked":
            self._set_state("Standby")

        self.log.info(f"user {self.current_username} logged out")
        self.current_username = None
        self.current_user_level = None
        self.current_user_allowed_medication = None
        return 0

    ################################
    #STATE
    ################################

    def _set_state(self, state):
        #private state setting method, for use by other functions inside the controller
        #the state check is here to catch bugs in controller code, not bad user input

        #returns status int: 0 success, 1 unknown state
        if state not in ALL_STATES:
            self.log.error(f"internal error, tried to set unknown state {state}")
            return 1

        changed_by = f"user {self.current_username}" if self.current_username else "controller"
        self.log.info(f"state changed from {self.state} to {state} by {changed_by}")
        self.state = state
        return 0

    def change_state(self, state):
        #external method for state setting, used when a logged in user requests a state change

        #returns status int: 0 success, 1 no user logged in, 2 unknown state, 3 access denied
        if self.current_username is None:
            self.log.warning(f"state change to {state} requested, no user is logged in")
            return 1

        if state not in ALL_STATES:
            self.log.warning(f"user {self.current_username} attempted to enter {state} state, state not found")
            return 2

        if state not in CAN_ENTER.get(self.current_user_level, []):
            self.log.warning(f"user {self.current_username} attempted to enter {state} state, access denied")
            return 3

        return self._set_state(state)

    ################################
    #USER MANAGEMENT
    #pass through to the authenticator, so other modules only need to talk to the controller
    ################################

    def add_user(self, username, password, level, allowed_medication=()):
        #returns status int: 0 success, 1 sys error, 2 user already exists (same as authenticator)
        return self.authenticator.add_user(username, password, level, allowed_medication)

    def delete_user(self, username):
        #returns status int: 0 success, 1 sys error, 2 user not found (same as authenticator)
        status = self.authenticator.delete_user(username)

        #a deleted user should not stay logged in
        if status == 0 and username == self.current_username:
            self.logout()
        return status

    def edit_user(self, username, **changes):
        #example: edit_user("bob", level="Nurse", allowed_medication=["advil"])
        #returns status int: 0 success, 1 sys error or invalid field, 2 user not found (same as authenticator)
        status = self.authenticator.edit_user(username, **changes)

        #keep the logged in user's info up to date, so changes apply without logging out
        if status == 0 and username == self.current_username:
            if "level" in changes:
                self.current_user_level = changes["level"]
            if "allowed_medication" in changes:
                self.current_user_allowed_medication = list(changes["allowed_medication"])
        return status

    def load_users(self):
        #returns a dict of all users, {username: {level, allowed_medication, ...}}, or None on sys error
        #passwords are not included, the authenticator's external load_users removes them
        try:
            return self.authenticator.load_users()
        except OSError as e:
            self.log.error(f"failed to load users: {e}")
            return None
