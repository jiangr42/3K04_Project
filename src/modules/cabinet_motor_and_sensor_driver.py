from modules.event_logger import EventLogger
from modules.status_codes import SUCCESS, ERROR, NOT_FOUND, ALREADY_EXISTS, INVALID_VALUE, PASSWORD_INCORRECT, LOCKED_OUT
from pathlib import Path
'''
place holder iun place of actual firmware that communciates with the motors
simualtes the interfaces

logging follows event_logger.py: DEBUG for sensor readings, INFO for cabinet open/close,
WARNING for unexpected but handled cases, ERROR for invalid requests
'''

CABINET_STATES = ("open", "closed", "fault")

class CabinetMotorAndSensorDriver:
    def __init__(self, number_of_cabinets):
        #create logger
        self.log = EventLogger().logger

        self.cabinets_states = []
        #array of drawer states. motors can be in "open" "closed" and "fault" states

        #for now, just insert in closed for now since no real sensor
        for i in range(number_of_cabinets):
            self.cabinets_states.append("closed")

        self.log.info(f"motor and sensor driver started with {number_of_cabinets} cabinets, all closed")

    def _valid_cabinet(self, cabinetID):
        #cabinets are numbered 1 to number of cabinets, bool is a subclass of int so it is rejected explicitly
        return (isinstance(cabinetID, int) and not isinstance(cabinetID, bool)
                and 1 <= cabinetID <= len(self.cabinets_states))

    def get_cabinets_states(self):
        self.log.debug(f"cabinet states read: {self.cabinets_states}")
        return self.cabinets_states

    def set_cabinets_states(self, cabinets_states : list):

        if "fault" in cabinets_states:
            self.log.warning(f"cabinet state set to {cabinets_states}")
        else:
            self.log.info(f"cabinet state set to {cabinets_states}")

        self.cabinets_states = cabinets_states

    def open_cabinet(self, cabinetID):

        previous = self.cabinets_states[cabinetID - 1]
        if previous == "open":
            self.log.warning(f"cabinet {cabinetID} open requested but it is already open")
        elif previous == "fault":
            self.log.warning(f"opening cabinet {cabinetID} while it is in fault")

        self.cabinets_states[cabinetID - 1] = "open"
        self.log.info(f"cabinet {cabinetID} opened")
        return SUCCESS

    def close_cabinet(self, cabinetID):

        previous = self.cabinets_states[cabinetID - 1]
        if previous == "closed":
            self.log.warning(f"cabinet {cabinetID} close requested but it is already closed")
        elif previous == "fault":
            self.log.warning(f"closing cabinet {cabinetID} while it is in fault")

        self.cabinets_states[cabinetID - 1] = "closed"
        self.log.info(f"cabinet {cabinetID} closed")
        return SUCCESS
