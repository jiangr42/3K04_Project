from modules.event_logger import EventLogger
from modules.status_codes import SUCCESS, ERROR, NOT_FOUND, INVALID_VALUE, REJECTED
from pathlib import Path
import yaml
import csv
import os
import threading

'''
PURPOSE

tracks medicine inventory across multiple cabinets
stores medicine quantities in an inventory CSV file

supports adding, dispensing, viewing, and resetting medicine quantities
logs inventory changes and errors through EventLogger

- cabinet IDs are the integers 1 to number_of_cabinets, set by the cabinet controller
  "1" is also accepted since the protocol sends IDs as strings, they are always returned as ints
- medicine names are stored lowercase so "Morphine" and "morphine" are the same medicine
- add and dispense are all or nothing, a request that can't be fully done changes nothing and returns REJECTED
- methods return codes from status_codes.py
'''

FIELDNAMES = ["cabinet", "medicine", "quantity"]

class InventoryTracker:
    def __init__(self, number_of_cabinets):
        #create logger
        self.log = EventLogger().logger

        #one read-change-write at a time, so two threads can't overwrite each other's changes
        self.lock = threading.Lock()

        #find inventory file location/path based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        inv_config = self.config["inventory"]
        inv_details_dir = project_root / inv_config["directory"]
        inv_details_dir.mkdir(parents=True, exist_ok=True)
        self.inv_file_path = inv_details_dir / inv_config["filename"]

        self.max_medicine_quantity = inv_config["max_medicine_quantity"]
        self.max_cabinet_quantity = inv_config["max_cabinet_quantity"]

        #cabinets are numbered 1 to number_of_cabinets
        if isinstance(number_of_cabinets, bool) or not isinstance(number_of_cabinets, int) or number_of_cabinets < 1:
            raise ValueError(f"number_of_cabinets must be a positive integer, got {number_of_cabinets!r}")
        self.number_of_cabinets = number_of_cabinets

        self.init_inv_details_file()

    def init_inv_details_file(self):
        # create the file with a header row if it doesn't exist yet
        if not self.inv_file_path.exists():
            self._write_rows([])
            self.log.info(f"created inv details file at {self.inv_file_path}")

    ################################
    #helpers
    ################################

    def _normalize_cabinet(self, cabinet):
        #returns the cabinet ID as an int from 1 to number_of_cabinets, or None if it is not a valid ID
        #bool is a subclass of int, so it has to be rejected explicitly
        if isinstance(cabinet, bool):
            return None
        if isinstance(cabinet, str):
            cabinet = cabinet.strip()
            if not cabinet.isdecimal():
                return None
            cabinet = int(cabinet)
        if not isinstance(cabinet, int) or not 1 <= cabinet <= self.number_of_cabinets:
            return None
        return cabinet

    @staticmethod
    def _normalize_medicine(medicine):
        #returns the medicine name lowercase, or None if it is not a valid name
        if not isinstance(medicine, str):
            return None
        medicine = medicine.strip().lower()
        return medicine or None

    @staticmethod
    def _valid_quantity(quantity):
        #bool is a subclass of int, so True would otherwise count as 1
        return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0

    def _read_rows(self):
        #reads and validates every row, quantities are returned as ints
        #raises ValueError if the file is malformed, so a bad file is reported instead of crashing the caller
        with open(self.inv_file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != FIELDNAMES:
                raise ValueError(f"inventory file header is {reader.fieldnames}, expected {FIELDNAMES}")

            rows = []
            seen = set()
            for line_number, row in enumerate(reader, start=2):
                cabinet = self._normalize_cabinet(row["cabinet"])
                medicine = self._normalize_medicine(row["medicine"])
                quantity = row["quantity"]
                #DictReader puts extra columns under the None key and fills missing ones with None
                if None in row or cabinet is None or medicine is None or quantity is None:
                    #an out of range cabinet also ends up here, for example if number_of_cabinets was lowered
                    raise ValueError(f"malformed inventory row on line {line_number} "
                                     f"(cabinets are 1 to {self.number_of_cabinets}): {row}")
                quantity = int(quantity)
                if quantity < 0:
                    raise ValueError(f"negative quantity on line {line_number}: {row}")
                #after normalizing, "Morphine" and "morphine" in the same cabinet would be two rows for one medicine
                if (cabinet, medicine) in seen:
                    raise ValueError(f"duplicate entry for {medicine} in cabinet {cabinet} on line {line_number}")
                seen.add((cabinet, medicine))
                rows.append({"cabinet": cabinet, "medicine": medicine, "quantity": quantity})
        return rows

    def _write_rows(self, rows):
        #writes to a temporary file first and then swaps it in
        #sorted by cabinet, then medicine name
        rows = sorted(rows, key=lambda row: (row["cabinet"], row["medicine"]))
        tmp_path = self.inv_file_path.with_name(self.inv_file_path.name + ".tmp")
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, self.inv_file_path)

    @staticmethod
    def _find_row(rows, cabinet, medicine):
        for row in rows:
            if row["cabinet"] == cabinet and row["medicine"] == medicine:
                return row
        return None

    ################################
    #public functions
    ################################

    def get_inventory(self, cabinet=None, medicine=None):
        #returns a list of rows ({"cabinet": int, "medicine": str, "quantity": int}), or None on error
        #cabinet and medicine are optional filters
        if cabinet is not None:
            cabinet = self._normalize_cabinet(cabinet)
            if cabinet is None:
                self.log.error("invalid cabinet filter for get_inventory")
                return None
        if medicine is not None:
            medicine = self._normalize_medicine(medicine)
            if medicine is None:
                self.log.error("invalid medicine filter for get_inventory")
                return None

        try:
            with self.lock:
                rows = self._read_rows()
        except (OSError, ValueError, csv.Error) as e:
            self.log.error(f"failed to retrieve inventory: {e}")
            return None

        return [row for row in rows
                if (cabinet is None or row["cabinet"] == cabinet)
                and (medicine is None or row["medicine"] == medicine)]

    def add_medicine(self, cabinet, medicine, quantity):
        #returns SUCCESS, INVALID_VALUE for bad input, REJECTED if it would go over a limit, ERROR on file errors
        cabinet = self._normalize_cabinet(cabinet)
        medicine = self._normalize_medicine(medicine)
        if cabinet is None or medicine is None or not self._valid_quantity(quantity):
            self.log.error(f"invalid add request, needs a cabinet from 1 to {self.number_of_cabinets}, "
                           f"a medicine name and a positive integer quantity")
            return INVALID_VALUE

        try:
            with self.lock:
                rows = self._read_rows()

                cabinet_total = sum(row["quantity"] for row in rows if row["cabinet"] == cabinet)
                row = self._find_row(rows, cabinet, medicine)
                current_quantity = row["quantity"] if row is not None else 0

                #all or nothing, so a request over either limit changes nothing
                if current_quantity + quantity > self.max_medicine_quantity:
                    self.log.warning(
                        f"rejected adding {quantity} of {medicine} to cabinet {cabinet}, "
                        f"would exceed the {self.max_medicine_quantity} per medicine limit (currently {current_quantity})"
                    )
                    return REJECTED
                if cabinet_total + quantity > self.max_cabinet_quantity:
                    self.log.warning(
                        f"rejected adding {quantity} of {medicine} to cabinet {cabinet}, "
                        f"would exceed the {self.max_cabinet_quantity} per cabinet limit (currently {cabinet_total})"
                    )
                    return REJECTED

                if row is not None:
                    row["quantity"] += quantity
                else:
                    rows.append({"cabinet": cabinet, "medicine": medicine, "quantity": quantity})

                self._write_rows(rows)

        except (OSError, ValueError, csv.Error) as e:
            self.log.error(f"failed to add {medicine} to cabinet {cabinet}: {e}")
            return ERROR

        self.log.info(f"added {quantity} of {medicine} to cabinet {cabinet}")
        return SUCCESS

    def dispense_medicine(self, cabinet, medicine, quantity):
        #returns SUCCESS, INVALID_VALUE for bad input, NOT_FOUND if the medicine isn't in the cabinet,
        #REJECTED if there isn't enough to dispense the full amount, ERROR on file errors
        cabinet = self._normalize_cabinet(cabinet)
        medicine = self._normalize_medicine(medicine)
        if cabinet is None or medicine is None or not self._valid_quantity(quantity):
            self.log.error(f"invalid dispense request, needs a cabinet from 1 to {self.number_of_cabinets}, "
                           f"a medicine name and a positive integer quantity")
            return INVALID_VALUE

        try:
            with self.lock:
                rows = self._read_rows()

                row = self._find_row(rows, cabinet, medicine)
                if row is None:
                    self.log.warning(f"{medicine} not found in cabinet {cabinet}")
                    return NOT_FOUND

                #never dispense part of a request, the user must know they did not get what they asked for
                if row["quantity"] < quantity:
                    self.log.warning(
                        f"rejected dispensing {quantity} of {medicine} from cabinet {cabinet}, "
                        f"only {row['quantity']} available"
                    )
                    return REJECTED

                row["quantity"] -= quantity
                self._write_rows(rows)

        except (OSError, ValueError, csv.Error) as e:
            self.log.error(f"failed to dispense {medicine} from cabinet {cabinet}: {e}")
            return ERROR

        self.log.info(f"dispensed {quantity} of {medicine} from cabinet {cabinet}")
        return SUCCESS

    def reset_medicine(self):
        #sets every medicine quantity to zero, the medicines stay listed
        #returns SUCCESS, or ERROR on file errors
        try:
            with self.lock:
                rows = self._read_rows()
                for row in rows:
                    row["quantity"] = 0
                self._write_rows(rows)

        except (OSError, ValueError, csv.Error) as e:
            self.log.error(f"failed to reset inventory: {e}")
            return ERROR

        self.log.info("all medicine quantities reset to zero")
        return SUCCESS
