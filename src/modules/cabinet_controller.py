from modules.event_logger import EventLogger
from modules.authenticator import Authenticator
from modules.status_codes import (SUCCESS, INVALID_VALUE, NOT_ALLOWED_IN_STATE, USER_ALREADY_LOGGED_IN,
                                  NOT_LOGGED_IN, ACCESS_DENIED)
#from modules.inventory_tracker import InventoryTracker
from modules.external_communication_driver import ExternalCommunicationDriver
from pathlib import Path
import yaml
import csv
import time
import threading
import functools

DEFAULT_ID = "000"

ALL_STATES = ["Standby", "Dispensing", "Restocking", "Maintenance", "Locked", "EmergencyShutdown", "Fault"]

######################################
#logic for user levels
######################################

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

#########################################
#helpers
#########################################

def _locked(method):
    #needed for solving simultanious access of system vars
    #runs the method while holding the controller's lock, so other threads can't change users or state at the same time
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper

class Cabinet_Controller:
    def __init__(self):
        ################################
        # state variables
        ################################
        self.ID = DEFAULT_ID
        self.lock = threading.RLock() #reentrant, since locked methods call each other (delete_user calls logout)
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
        self.external_communication_driver = ExternalCommunicationDriver(self)
        self.external_communication_driver.start()

        #need to add more stuff

    ################################
    #LOGIN/OUT
    ################################

    @_locked
    def username_password_login(self, username, password):
        #logs in a user, called by the GUI when it gets a log in request
        #only decides if the user can log in during the current state, does not change state

        #returns status code: SUCCESS, PASSWORD_INCORRECT, NOT_FOUND, LOCKED_OUT (from authenticator),
        #NOT_ALLOWED_IN_STATE, or USER_ALREADY_LOGGED_IN

        #checked before the authenticator so a rejected log in doesn't count as a failed attempt
        if self.current_username is not None:
            self.log.warning(f"user {username} attempted log in, user {self.current_username} is already logged in")
            return USER_ALREADY_LOGGED_IN

        status, level, allowed_medication = self.authenticator.check_username_password(username, password)
        return self._complete_login(username, status, level, allowed_medication)

    @_locked
    def username_login(self, username):
        #logs in a user, called by the card reader when it gets a log in request
        #no password needed, having the card is the proof of identity
        #only decides if the user can log in during the current state, does not change state

        #returns status code: SUCCESS, NOT_FOUND (from authenticator), NOT_ALLOWED_IN_STATE, or USER_ALREADY_LOGGED_IN
        if self.current_username is not None:
            self.log.warning(f"user {username} attempted log in, user {self.current_username} is already logged in")
            return USER_ALREADY_LOGGED_IN

        status, level, allowed_medication = self.authenticator.check_username(username)
        return self._complete_login(username, status, level, allowed_medication)

    def _complete_login(self, username, status, level, allowed_medication):
        #takes the result of the authenticator check
        #returns the authenticator status if it failed, NOT_ALLOWED_IN_STATE, or SUCCESS
        if status != SUCCESS:
            return status

        #role check is done after the credential check so it doesn't reveal anything to someone without valid credentials
        if self.state not in LOGIN_ALLOWED_IN.get(level, []):
            self.log.warning(f"user {username} with level {level} not allowed to log in during state {self.state}")
            return NOT_ALLOWED_IN_STATE

        #update vars when log in successful
        self.current_username = username
        self.current_user_level = level
        self.current_user_allowed_medication = allowed_medication
        self.log.info(f"user {username} logged in, level {level}, state {self.state}")
        return SUCCESS

    @_locked
    def logout(self):
        #logs out the current user and returns the cabinet to Standby
        #Fault and EmergencyShutdown also go back to Standby, if the problem is still there the controller will detect it again
        #Locked stays Locked, so an admin logging in and out doesn't unlock the cabinet

        #returns status code: SUCCESS or NOT_LOGGED_IN
        if self.current_username is None:
            self.log.warning("log out requested, no user is logged in")
            return NOT_LOGGED_IN

        if self.state != "Locked":
            self._set_state("Standby")

        self.log.info(f"user {self.current_username} logged out")
        self.current_username = None
        self.current_user_level = None
        self.current_user_allowed_medication = None
        return SUCCESS

    ################################
    #STATE
    ################################

    def _set_state(self, state):
        #private state setting method, for use by other functions inside the controller
        #the state check is here to catch bugs in controller code, not bad user input

        #returns status code: SUCCESS or INVALID_VALUE (unknown state)
        if state not in ALL_STATES:
            self.log.error(f"internal error, tried to set unknown state {state}")
            return INVALID_VALUE

        changed_by = f"user {self.current_username}" if self.current_username else "controller"
        self.log.info(f"state changed from {self.state} to {state} by {changed_by}")
        self.state = state
        return SUCCESS

    @_locked
    def change_state(self, state):
        #external method for state setting, used when a logged in user requests a state change

        #returns status code: SUCCESS, NOT_LOGGED_IN, INVALID_VALUE (unknown state), or ACCESS_DENIED
        if self.current_username is None:
            self.log.warning(f"state change to {state} requested, no user is logged in")
            return NOT_LOGGED_IN

        if state not in ALL_STATES:
            self.log.warning(f"user {self.current_username} attempted to enter {state} state, state not found")
            return INVALID_VALUE

        if state not in CAN_ENTER.get(self.current_user_level, []):
            self.log.warning(f"user {self.current_username} attempted to enter {state} state, access denied")
            return ACCESS_DENIED

        return self._set_state(state)

    ################################
    #USER MANAGEMENT
    #pass through to the authenticator, so other modules only need to talk to the controller
    ################################

    @_locked
    def add_user(self, username, password, level, allowed_medication=()):
        #returns status code: SUCCESS, ERROR (sys error), ALREADY_EXISTS (same as authenticator), or INVALID_VALUE (unknown level)
        if level not in LOGIN_ALLOWED_IN:
            self.log.warning(f"user {username} cannot be added, unknown level {level}")
            return INVALID_VALUE

        return self.authenticator.add_user(username, password, level, allowed_medication)

    @_locked
    def delete_user(self, username):
        #returns status code: SUCCESS, ERROR (sys error), or NOT_FOUND (same as authenticator)
        status = self.authenticator.delete_user(username)

        #a deleted user should not stay logged in
        if status == SUCCESS and username == self.current_username:
            self.logout()
        return status

    @_locked
    def edit_user(self, username, **changes):
        #example: edit_user("bob", level="Nurse", allowed_medication=["advil"])
        #returns status code: SUCCESS, ERROR (sys error), INVALID_VALUE (invalid field), or NOT_FOUND (same as authenticator)
        status = self.authenticator.edit_user(username, **changes)

        #keep the logged in user's info up to date, so changes apply without logging out
        if status == SUCCESS and username == self.current_username:
            if "level" in changes:
                self.current_user_level = changes["level"]
            if "allowed_medication" in changes:
                self.current_user_allowed_medication = list(changes["allowed_medication"])
        return status

    @_locked
    def load_users(self):
        #returns a dict of all users, {username: {level, allowed_medication, ...}}, or None on sys error
        #passwords are not included, the authenticator's external load_users removes them
        try:
            return self.authenticator.load_users()
        except OSError as e:
            self.log.error(f"failed to load users: {e}")
            return None
