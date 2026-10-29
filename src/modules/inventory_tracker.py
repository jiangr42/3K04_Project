from modules.event_logger import EventLogger
from pathlib import Path
import yaml
import csv



class InventoryTracker:
    def __init__(self):
        #create logger
        self.log = EventLogger().logger

        #find auth file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        inv_config = self.config["invevntory"]
        inv_details_dir = project_root / inv_config["directory"]
        inv_details_dir.mkdir(parents=True, exist_ok=True)
        self.inv_file_path = inv_details_dir / inv_config["filename"]

    def getInventory(self):
        
        return 0

    def addMedicine(self, cabinet, medicine, quantity):
        '''add a medicine'''
        return 0

    def dispenseMedicine(self, cabinet, medicine, quantity):
        '''dispense a medicine'''
        return 0
    
    def resetMedicine(self):
        '''
        for medicine in cabinet:
            medicine quantity = 0
        '''
        return 0
    