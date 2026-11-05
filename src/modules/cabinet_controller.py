from modules.event_logger import EventLogger
from modules.authenticator import Authenticator
from modules.status_codes import (SUCCESS, ERROR, INVALID_VALUE, REJECTED, NOT_ALLOWED_IN_STATE, USER_ALREADY_LOGGED_IN,
                                  NOT_LOGGED_IN, ACCESS_DENIED)
from modules.inventory_tracker import InventoryTracker
from modules.external_motor_driver import CabinetMotorAndSensorDriver
from modules.external_communication_driver import ExternalCommunicationDriver
from pathlib import Path
import yaml
import csv
import time
import threading
import functools

DEFAULT_ID = "000"
NUMBER_OF_CABINETS = 4 #cabinets are numbered 1 to NUMBER_OF_CABINETS

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

#user levels allowed to handle medication, admin and maintenance cannot access meds
CAN_ACCESS_MEDICATION = ["Nurse"]

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
        self.number_of_cabinets = NUMBER_OF_CABINETS
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
        self.inventory_tracker = InventoryTracker(self.number_of_cabinets)
        self.motor_driver = CabinetMotorAndSensorDriver(self.number_of_cabinets)
        #started last, its thread can call into the controller as soon as it starts
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

        #no cabinet should be left open once the user walks away
        self._close_all_cabinets()

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

    ################################
    #MEDICATION
    #checks that the logged in user can do the request, then updates the inventory and opens the cabinet
    ################################

    def _parse_cabinet(self, cabinet):
        #returns the cabinet as an int from 1 to number_of_cabinets, or None if it is not valid
        #"1" is accepted since the protocol sends cabinet IDs as strings
        if isinstance(cabinet, str) and cabinet.strip().isdecimal():
            cabinet = int(cabinet)
        if isinstance(cabinet, bool) or not isinstance(cabinet, int) or not 1 <= cabinet <= self.number_of_cabinets:
            return None
        return cabinet

    def _check_medication_request(self, action, required_state, cabinet, medicine):
        #shared checks for add and dispense, logs the reason for any rejection with the user who made the request
        #returns (status, cabinet, medicine), cabinet and medicine are normalized when status is SUCCESS
        user = self.current_username
        if user is None:
            self.log.warning(f"{action} of {medicine} in cabinet {cabinet} requested, no user is logged in")
            return NOT_LOGGED_IN, None, None

        if self.current_user_level not in CAN_ACCESS_MEDICATION:
            self.log.warning(f"user {user} with level {self.current_user_level} attempted {action}, access denied")
            return ACCESS_DENIED, None, None

        if self.state != required_state:
            self.log.warning(f"user {user} attempted {action} during state {self.state}, needs state {required_state}")
            return NOT_ALLOWED_IN_STATE, None, None

        parsed_cabinet = self._parse_cabinet(cabinet)
        if parsed_cabinet is None:
            self.log.warning(f"user {user} attempted {action} with invalid cabinet {cabinet!r}, "
                             f"cabinets are 1 to {self.number_of_cabinets}")
            return INVALID_VALUE, None, None

        if not isinstance(medicine, str) or not medicine.strip():
            self.log.warning(f"user {user} attempted {action} with invalid medicine {medicine!r}")
            return INVALID_VALUE, None, None
        medicine = medicine.strip().lower() #same as the inventory tracker, names are stored lowercase

        allowed = [med.strip().lower() for med in (self.current_user_allowed_medication or [])]
        if medicine not in allowed:
            self.log.warning(f"user {user} attempted {action} of {medicine}, not in their allowed medication")
            return ACCESS_DENIED, None, None

        if self.motor_driver.get_cabinets_states()[parsed_cabinet - 1] == "fault":
            self.log.warning(f"user {user} attempted {action} of {medicine} in cabinet {parsed_cabinet}, cabinet is in fault")
            return REJECTED, None, None

        return SUCCESS, parsed_cabinet, medicine

    @_locked
    def dispense_medicine(self, cabinet, medicine, quantity):
        #dispenses medicine for the logged in user, needs Dispensing state and the medicine in the user's allowed medication
        #the cabinet is opened once the inventory is updated, and stays open until close_cabinet or log out

        #returns status code: SUCCESS, NOT_LOGGED_IN, ACCESS_DENIED, NOT_ALLOWED_IN_STATE, INVALID_VALUE,
        #REJECTED (not enough stock or cabinet in fault), NOT_FOUND, or ERROR (same as inventory tracker)
        status, cabinet, medicine = self._check_medication_request("dispense", "Dispensing", cabinet, medicine)
        if status != SUCCESS:
            return status

        status = self.inventory_tracker.dispense_medicine(cabinet, medicine, quantity)
        if status != SUCCESS:
            self.log.warning(f"user {self.current_username} failed to dispense {quantity!r} of {medicine} "
                             f"from cabinet {cabinet}, status {status}")
            return status

        if self.motor_driver.open_cabinet(cabinet) != SUCCESS:
            #the medicine never left the cabinet, so put it back in the inventory
            self.log.error(f"cabinet {cabinet} failed to open for user {self.current_username}, undoing dispense of {medicine}")
            if self.inventory_tracker.add_medicine(cabinet, medicine, quantity) != SUCCESS:
                self.log.error(f"failed to undo dispense of {quantity} of {medicine} in cabinet {cabinet}, inventory is off")
            return ERROR

        self.log.info(f"user {self.current_username} dispensed {quantity} of {medicine} from cabinet {cabinet}")
        return SUCCESS

    @_locked
    def add_medicine(self, cabinet, medicine, quantity):
        #restocks medicine for the logged in user, needs Restocking state and the medicine in the user's allowed medication
        #the cabinet is opened once the inventory is updated, and stays open until close_cabinet or log out

        #returns status code: SUCCESS, NOT_LOGGED_IN, ACCESS_DENIED, NOT_ALLOWED_IN_STATE, INVALID_VALUE,
        #REJECTED (over a limit or cabinet in fault), or ERROR (same as inventory tracker)
        status, cabinet, medicine = self._check_medication_request("restock", "Restocking", cabinet, medicine)
        if status != SUCCESS:
            return status

        status = self.inventory_tracker.add_medicine(cabinet, medicine, quantity)
        if status != SUCCESS:
            self.log.warning(f"user {self.current_username} failed to restock {quantity!r} of {medicine} "
                             f"in cabinet {cabinet}, status {status}")
            return status

        if self.motor_driver.open_cabinet(cabinet) != SUCCESS:
            #the medicine could not be put in, so take it back out of the inventory
            self.log.error(f"cabinet {cabinet} failed to open for user {self.current_username}, undoing restock of {medicine}")
            if self.inventory_tracker.dispense_medicine(cabinet, medicine, quantity) != SUCCESS:
                self.log.error(f"failed to undo restock of {quantity} of {medicine} in cabinet {cabinet}, inventory is off")
            return ERROR

        self.log.info(f"user {self.current_username} restocked {quantity} of {medicine} in cabinet {cabinet}")
        return SUCCESS

    @_locked
    def close_cabinet(self, cabinet):
        #closes a cabinet after the user is done with it
        #returns status code: SUCCESS, NOT_LOGGED_IN, or INVALID_VALUE
        if self.current_username is None:
            self.log.warning(f"close of cabinet {cabinet} requested, no user is logged in")
            return NOT_LOGGED_IN

        parsed_cabinet = self._parse_cabinet(cabinet)
        if parsed_cabinet is None:
            self.log.warning(f"user {self.current_username} attempted to close invalid cabinet {cabinet!r}")
            return INVALID_VALUE

        status = self.motor_driver.close_cabinet(parsed_cabinet)
        if status == SUCCESS:
            self.log.info(f"user {self.current_username} closed cabinet {parsed_cabinet}")
        return status

    def _close_all_cabinets(self):
        #closes every open cabinet, used on log out
        for index, cabinet_state in enumerate(self.motor_driver.get_cabinets_states()):
            if cabinet_state == "open":
                self.log.info(f"closing cabinet {index + 1} left open by user {self.current_username}")
                self.motor_driver.close_cabinet(index + 1)
