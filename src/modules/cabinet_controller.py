from modules.event_logger import EventLogger
from modules.authenticator import Authenticator
from pathlib import Path
import yaml
import csv
import time

class Cabinet_Controller:
    def __init__(self):
        #create logger
        self.log = EventLogger().logger

        self.authenticator = Authenticator()