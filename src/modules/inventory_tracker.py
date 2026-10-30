from modules.event_logger import EventLogger
from pathlib import Path
import yaml
import csv

FIELDNAMES = ["cabinet", "medicine", "quantity"]

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

        self.init_inv_details_file()

    def init_inv_details_file(self):
        # create the file with a header row if it doesn't exist yet
        if not self.inv_path.exists():
            with open(self.inv_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
            self.log.info(f"created inv details file at {self.inv_path}")

    def get_inventory(self):
        
        return 0

    def add_medicine(self, cabinet, medicine, quantity):
        '''add a medicine
        
        self.cabinet.medicine += medicine.quantity


        '''
       
        # if success return 0, if sys error or invalid input return 1
        try:
            # read every row from the inventory file
            with open(self.inv_file_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            # check if medicine already exists in the specified cabinet
            for row in rows:
                if row["cabinet"] == str(cabinet) and row["medicine"] == medicine:
                    row["quantity"] = str(int(row["quantity"]) + quantity) # add medicine
                    break
            else:
                # medicine doesn't exist in cabinet, create a new row
                rows.append({
                    "cabinet": str(cabinet),
                    "medicine": medicine,
                    "quantity": str(quantity)
                })

            # rewrite the inventory file with updated quantities
            with open(self.inv_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)

        except (OSError, ValueError) as e:
            self.log.error(f"failed to add {medicine} to cabinet {cabinet}: {e}")
            return 1

        self.log.info(f"added {quantity} of {medicine} to cabinet {cabinet}")
        return 0


    def dispense_medicine(self, cabinet, medicine, quantity):
        # if success return 0, if sys error or invalid input return 1
        # if medicine not found return 2

        if quantity <= 0:
            self.log.error("dispense quantity must be positive")
            return 1

        try:
            # read every row from the inventory file
            with open(self.inv_file_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            # find the medicine in the specified cabinet
            for row in rows:
                if row["cabinet"] == str(cabinet) and row["medicine"] == medicine:

                    available = int(row["quantity"])

                    # determine how much medicine can be dispensed
                    dispensed = min(quantity, available)

                    # update the remaining quantity
                    row["quantity"] = str(available - dispensed)

                    if dispensed < quantity:
                        self.log.warning(
                            f"insufficient {medicine} in cabinet {cabinet}. "
                            f"requested {quantity}, dispensed {dispensed}"
                        )
                    else:
                        self.log.info(
                            f"dispensed {dispensed} of {medicine} from cabinet {cabinet}"
                        )

                    break

            else:
                self.log.warning(f"{medicine} not found in cabinet {cabinet}")
                return 2

            # rewrite the inventory file with updated quantities
            with open(self.inv_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)

        except (OSError, ValueError) as e:
            self.log.error(f"failed to dispense {medicine}: {e}")
            return 1

        return 0
    
    def reset_medicine(self):
        '''
        for medicine in cabinet:
            medicine quantity = 0
        '''
        return 0
    