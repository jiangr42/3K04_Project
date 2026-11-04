from modules.event_logger import EventLogger
from pathlib import Path
import yaml
import csv

MAX_MEDICINE_QUANTITY = 100
MAX_CABINET_QUANTITY = 100

'''
PURPOSE

tracks medicine inventory across multiple cabinets
stores medicine quantities in an inventory CSV file

supports adding, dispensing, viewing, and resetting medicine quantities
logs inventory changes and errors through EventLogger
'''

FIELDNAMES = ["cabinet", "medicine", "quantity"]

class InventoryTracker:
    def __init__(self):
        #create logger
        self.log = EventLogger().logger

        #find inventory file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        inv_config = self.config["inventory"]
        inv_details_dir = project_root / inv_config["directory"]
        inv_details_dir.mkdir(parents=True, exist_ok=True)
        self.inv_file_path = inv_details_dir / inv_config["filename"]

        self.init_inv_details_file()

    def init_inv_details_file(self):
        # create the file with a header row if it doesn't exist yet
        if not self.inv_file_path.exists():
            with open(self.inv_file_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
            self.log.info(f"created inv details file at {self.inv_file_path}")

    def get_inventory(self):
        # returns all inventory details
        try:
            with open(self.inv_file_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        except OSError as e:
            self.log.error(f"Failed to retrieve inventory: {e}")
            return None

        return rows

    def add_medicine(self, cabinet, medicine, quantity):
        """Add medicine to inventory, respecting quantity limits."""

        # Check that quantity is valid
        if not isinstance(quantity, int) or quantity <= 0:
            self.log.error("Invalid quantity entered.")
            return 1

        try:
            # Read existing inventory
            with open(self.inv_file_path, "r", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            # Calculate remaining cabinet capacity
            cabinet_total = sum(
                int(row["quantity"])
                for row in rows
                if row["cabinet"] == str(cabinet)
            )

            cabinet_space = MAX_CABINET_QUANTITY - cabinet_total

            # Find existing medicine
            for row in rows:
                if row["cabinet"] == str(cabinet) and row["medicine"] == medicine:

                    current_quantity = int(row["quantity"])

                    # Calculate remaining space for this medicine
                    medicine_space = MAX_MEDICINE_QUANTITY - current_quantity

                    # Add the maximum amount allowed by both limits
                    amount_to_add = min(quantity, medicine_space, cabinet_space)

                    row["quantity"] = str(current_quantity + amount_to_add)

                    if amount_to_add < quantity:
                        self.log.warning(
                            f"Could not add full quantity of {medicine}. "
                            f"Only added {amount_to_add} of {quantity} requested."
                        )

                    break

            else:
                # Medicine does not exist in this cabinet
                amount_to_add = min(
                    quantity,
                    MAX_MEDICINE_QUANTITY,
                    cabinet_space
                )

                if amount_to_add > 0:
                    rows.append({
                        "cabinet": str(cabinet),
                        "medicine": medicine,
                        "quantity": str(amount_to_add)
                    })

                if amount_to_add < quantity:
                    self.log.warning(
                        f"Could not add full quantity of {medicine}. "
                        f"Only added {amount_to_add} of {quantity} requested."
                    )

            # Sort inventory by cabinet, then medicine name
            rows.sort(
                key=lambda row: (int(row["cabinet"]), row["medicine"].lower())
            )

            # Write updated inventory
            with open(self.inv_file_path, "w", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["cabinet", "medicine", "quantity"]
                )
                writer.writeheader()
                writer.writerows(rows)

            self.log.info(f"Added {amount_to_add} of {medicine} to cabinet {cabinet}.")
            return 0

        except (OSError, ValueError) as e:
            self.log.error(f"Error adding medicine: {e}")
            return 1

    def dispense_medicine(self, cabinet, medicine, quantity):
        # if success return 0, if sys error or invalid input return 1
        # if medicine not found return 2

        if not isinstance(quantity, int) or quantity <= 0:
            self.log.error("invalid dispense quantity, must be a positive integer")
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
                        self.log.info(f"dispensed {dispensed} of {medicine} from cabinet {cabinet}")

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
            self.log.error(f"failed to dispense {medicine} from cabinet {cabinet}: {e}")
            return 1

        return 0
    
    def reset_medicine(self):
        # if success return 0, if sys error return 1

        try:
            # rewrite the inventory file with only the header row
            with open(self.inv_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()

        except OSError as e:
            self.log.error(f"failed to reset inventory: {e}")
            return 1

        self.log.info("all inventory entries deleted")
        return 0
    