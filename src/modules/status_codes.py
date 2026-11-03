'''
PURPOSE

status codes shared by every module, so a code means the same thing no matter which function returned it

0-8 are the protocol codes, see communication_protocol.md 
9 and up are only used inside the controller (log in and state changes), they are never sent over serial
'''

#protocol codes
SUCCESS = 0
ERROR = 1 #internal or system error, for example a file could not be read or written
NOT_FOUND = 2
ALREADY_EXISTS = 3
INVALID_REQUEST = 4 #malformed message
UNKNOWN_TARGET = 5
INVALID_VALUE = 6 #wrong type or out of range value, for example an unknown state or field
REJECTED = 7 #valid but not allowed in the current state
WRONG_DEVICE = 8

#internal codes
PASSWORD_INCORRECT = 9
LOCKED_OUT = 10 #too many failed log in attempts
NOT_ALLOWED_IN_STATE = 11 #user's level can't log in during the current state
USER_ALREADY_LOGGED_IN = 12 #another user is logged in
NOT_LOGGED_IN = 13 #action needs a logged in user
ACCESS_DENIED = 14 #user's level can't do this

#dict for code to string
STATUS_NAMES = {
    SUCCESS: "SUCCESS",
    ERROR: "ERROR",
    NOT_FOUND: "NOT_FOUND",
    ALREADY_EXISTS: "ALREADY_EXISTS",
    INVALID_REQUEST: "INVALID_REQUEST",
    UNKNOWN_TARGET: "UNKNOWN_TARGET",
    INVALID_VALUE: "INVALID_VALUE",
    REJECTED: "REJECTED",
    WRONG_DEVICE: "WRONG_DEVICE",
    PASSWORD_INCORRECT: "PASSWORD_INCORRECT",
    LOCKED_OUT: "LOCKED_OUT",
    NOT_ALLOWED_IN_STATE: "NOT_ALLOWED_IN_STATE",
    USER_ALREADY_LOGGED_IN: "USER_ALREADY_LOGGED_IN",
    NOT_LOGGED_IN: "NOT_LOGGED_IN",
    ACCESS_DENIED: "ACCESS_DENIED",
}
