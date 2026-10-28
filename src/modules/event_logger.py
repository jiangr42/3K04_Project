from pathlib import Path
import yaml
import logging

'''
USAGE:

log = EventLogger().logger
log.info("Cabinet unlocked by user XXXXXXX")

'''

class EventLogger:
    def __init__(self):
        #set up logging file based on configs
        project_root = Path(__file__).resolve().parents[1]
        with open(project_root / "config" / "config.yaml") as f:
            self.config = yaml.safe_load(f) #load the config file

        log_config = self.config["logging"]
        log_dir = project_root / log_config["directory"]
        log_dir.mkdir(parents=True, exist_ok=True)
        self.output_file_path = log_dir / log_config["filename"]

        #create logger
        self.logger = logging.getLogger("event_logger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        #add handlers
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            #file handler so it logs to a file
            fh = logging.FileHandler(self.output_file_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)

            #console handler for printouts
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)

            self.logger.addHandler(fh)
            self.logger.addHandler(ch)