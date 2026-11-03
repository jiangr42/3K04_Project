from modules.serial_driver import SerialDriver
from modules.event_logger import EventLogger
from modules.status_codes import (STATUS_NAMES, SUCCESS, ERROR, NOT_FOUND, INVALID_REQUEST, UNKNOWN_TARGET,
                                  INVALID_VALUE, WRONG_DEVICE)
from pathlib import Path
import yaml
import json
import threading
'''
- talks to serial driver, which exposes send(), read(), read_all(), and status()
status gives back either
"Ready" - ready for TX/RX
"Reconnecting" -attempting reconnections
"Off" -serial module is not active

- parses the data received and calls cabinet controller functions

- is a separate thread that constantly reads from the serial driver
'''

REQUIRED_FIELDS = ["device_id", "type", "target"]

class ExternalCommunicationDriver:
    def __init__(self, cabinet_controller):
        #vars
        self.running= False #True while the listener thread is alive
        self.cabinet_controller = cabinet_controller

        #create logger
        self.log = EventLogger().logger

        #load configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        self.poll_interval = self.config["external_communication"]["poll_interval"]

        #instances of comm methods
        self.serialDriver = None

        #thread handling
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        #starts the comm methods and the listener thread, does nothing if already running
        if self._thread is not None and self._thread.is_alive():
            self.log.warning("External communication driver start() called while already running")
            return

        #load comm method settings
        serial_config = self.config["serial"]

        #open comm method
        self.serialDriver = SerialDriver(
            port=serial_config["port"],
            baudrate=serial_config["baudrate"],
            bytesize=serial_config["bytesize"],
            parity=serial_config["parity"],
            stopbits=serial_config["stopbits"],
            timeout=serial_config["timeout"],
            write_timeout=serial_config["write_timeout"],
            xonxoff=serial_config["xonxoff"],
            rtscts=serial_config["rtscts"],
            dsrdtr=serial_config["dsrdtr"],
            line_ending=serial_config["line_ending"],
            rx_queue_size=serial_config["rx_queue_size"],
        )
        self.serialDriver.open()

        #start listener thread, daemon so it never keeps the program alive on exit
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="ExternalCommunicationDriver", daemon=True)
        self._thread.start()

        self.running = True
        self.log.info("External communication driver started")

    def stop(self):
        #stops the listener thread and closes the comm methods
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

        if self.serialDriver is not None:
            self.serialDriver.close()
            self.serialDriver = None

        self.running = False
        self.log.info("External communication driver stopped")

    def is_running(self):
        return self.running

    def _run(self):
        #listener loop, runs on its own thread until stop() is called
        while not self._stop_event.is_set():
            if self.serialDriver.get_status() == "Ready":
                for message in self.serialDriver.read_all():
                    #a bug in one handler should be logged, not kill the thread and stop all communication
                    try:
                        self._handle_message(message)
                    except Exception:
                        self.log.exception(f"unhandled error while handling message: {message}")
                        try:
                            self._send_response(None, ERROR, data={"errorMessage": "INTERNAL ERROR WHILE HANDLING REQUEST"})
                        except Exception:
                            self.log.exception("failed to send error response")

            #wait() to not take up all resources
            self._stop_event.wait(self.poll_interval)

    def _send_response(self, target, status, field=None, data=None):
        #builds a response in the format from communication_protocol.md and sends it
        response = {
            "device_id": self.cabinet_controller.ID, #always this controller's own ID, even in error responses
            "type": "response",
            "target": target, 
            "status": status,
            "status_name": STATUS_NAMES[status],
        }
        if field is not None:
            response["field"] = field
        if data is not None:
            response["data"] = data
        self.serialDriver.send(json.dumps(response))

    def _handle_message(self, message):
        #parse a received message and call the matching controller function
        #every request gets exactly one response, so every branch below sends one and returns
        try:
            messageDict = json.loads(message)
            #valid JSON can still be a number or list, a request must be an object
            if not isinstance(messageDict, dict):
                raise ValueError("message is not a JSON object")
        except ValueError:
            #if cannot be parsed as a json object, indicate it
            self._send_response(None, INVALID_REQUEST, data={"errorMessage": "COULD NOT DECODE MESSAGE AS A JSON OBJECT"})
            return

        #check if all the required fields are there, if not send back error message
        missing = [key for key in REQUIRED_FIELDS if key not in messageDict]
        if missing:
            self._send_response(messageDict.get("target"), INVALID_REQUEST, data={"errorMessage": f"MISSING REQUIRED FIELDS: {missing}"})
            return

        device_id = messageDict["device_id"]
        request_type = messageDict["type"]
        target = messageDict["target"]
        params = messageDict.get("params", {}) #params is optional
        if not isinstance(params, dict):
            self._send_response(target, INVALID_REQUEST, data={"errorMessage": "PARAMS MUST BE A JSON OBJECT"})
            return

        if request_type not in ("get", "set"):
            self._send_response(target, INVALID_REQUEST, data={"errorMessage": f"UNKNOWN TYPE: {request_type}"})
            return

        #check for the right device ID, "*" is only allowed for get controller_state (protocol section 3.1)
        discovery_allowed = device_id == "*" and request_type == "get" and target == "controller_state"
        if device_id != self.cabinet_controller.ID and not discovery_allowed:
            self._send_response(target, WRONG_DEVICE)
            return

        match (request_type, target):
            case ("get", "auth_details"):
                self._get_auth_details(params)

            case ("set", "auth_details"):
                self._set_auth_details(params)

            #other targets to be implemented

            case _:
                self._send_response(target, UNKNOWN_TARGET, data={"errorMessage": f"UNKNOWN TARGET FOR {request_type}: {target}"})

    def _get_auth_details(self, params):
        username = params.get("username") #optional, all users if not given
        if username is not None and not isinstance(username, str):
            self._send_response("auth_details", INVALID_VALUE, data={"errorMessage": "username MUST BE A STRING"})
            return

        users = self.cabinet_controller.load_users() #passwords already removed
        if users is None:
            self._send_response("auth_details", ERROR, data={"errorMessage": "COULD NOT LOAD USERS"})
            return

        if username is not None:
            if username not in users:
                self._send_response("auth_details", NOT_FOUND, data={"errorMessage": f"USER {username} NOT FOUND"})
                return
            users = {username: users[username]}

        user_list = [{"username": name, **details} for name, details in users.items()]
        self._send_response("auth_details", SUCCESS, data={"users": user_list})

    def _set_auth_details(self, params):
        match params.get("action"):
            case "add":
                username = params.get("username")
                password = params.get("password")
                level = params.get("level")
                allowed_medication = params.get("allowed_medication", [])

                #check if fields are present
                if username is None or password is None or level is None:
                    self._send_response("auth_details", INVALID_REQUEST, field=username, data={"errorMessage": "ADD user NEEDS username, password AND level"})
                    return

                #a string here would be split into letters by tuple(), so it must be a list of strings
                if (not all(isinstance(value, str) for value in (username, password, level))
                        or not isinstance(allowed_medication, list)
                        or not all(isinstance(med, str) for med in allowed_medication)):
                    self._send_response("auth_details", INVALID_VALUE, field=username, data={"errorMessage": "INVALID VALUE IN ADD REQUEST"})
                    return

                status = self.cabinet_controller.add_user(username, password, level, tuple(allowed_medication))
                #controller returns shared status codes, so the result is sent as is
                self._send_response("auth_details", status, field=username)

            #edit and delete to be implemented

            case None:
                self._send_response("auth_details", INVALID_REQUEST, data={"errorMessage": "MISSING action"})

            case action:
                self._send_response("auth_details", INVALID_VALUE, data={"errorMessage": f"UNKNOWN ACTION: {action}"})

'''
**Add**
Management system request:
```json
{ "device_id": "000", "type": "set", "target": "auth_details",
  "params": { "action": "add", "username": "amy", "password": "pw123", "level": "Admin", "allowed_medication": ["morphine"] } }
```

```json
{ "device_id": "ADC-01", "type": "response", "target": "auth_details",
  "status": 0, "status_name": "SUCCESS", "field": "amy" }
'''