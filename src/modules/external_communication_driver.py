from modules.serial_driver import SerialDriver
from modules.event_logger import EventLogger
from modules.status_codes import (STATUS_NAMES, SUCCESS, ERROR, NOT_FOUND, INVALID_REQUEST, UNKNOWN_TARGET,
                                  INVALID_VALUE, WRONG_DEVICE)
from pathlib import Path
import yaml
import json
import threading
'''
- run as separate thread. every time increment,
  fetch data, and send it in serial
- receive communication

'''

