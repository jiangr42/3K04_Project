from pathlib import Path
import yaml
import logging


'''
private:
self.log -> self.log = EventLogger.logger
self.inventory_file_path -> authenticator lines 22-29 __init__

public:
get_inventory()
add_medicine(cabinet, amount)
dispense_medicine(cabinet, amouont)
reset_inventory()
'''


class EventLogger:
    def __init__(self):
        #create logger
        self.log = EventLogger.logger

        #find auth file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        auth_config = self.config["authentication"]
        auth_details_dir = project_root / auth_config["auth_details"]["directory"]
        auth_details_dir.mkdir(parents=True, exist_ok=True)
        self.output_file_path = auth_details_dir / auth_config["auth_details"]["filename"]

    def getInventory(self):
        #asdf

    def addMedicine(self, cabinet, quantity):
        #asdf

    def dispenseMedicine(self, cabinet, quantity):
        #asdf
    
    def resetMedicine(self):
        #asdf
    