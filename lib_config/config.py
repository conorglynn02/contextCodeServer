import json
import os
import logging
from logging.handlers import RotatingFileHandler
import colorlog

class ColourConfig:
    DEBUG: str
    INFO: str
    WARNING: str
    ERROR: str
    CRITICAL: str

class ConsoleOutput:
    enabled: bool
    level: str
    format: str
    date_format: str
    colour: ColourConfig

class FileOutput:
    enabled: bool
    level: str
    format: str
    date_format: str
    log_dir: str
    filename: str
    max_bytes: int
    backup_count: int

class DatabaseConfig:
    host: str
    port: int

class LoggingConfig:
    console_output: ConsoleOutput
    file_output: FileOutput

class Config:
    database: DatabaseConfig
    logging_config: LoggingConfig

    hasError: bool

    def __init__(self, config_path: str = "lib_config/config.json"):
        self.set_up_config(config_path)
        self.set_up_logger()
        hasError = False

    def set_up_config(self, config_path):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path) as file:
            self.data = json.load(file)

    def __getattr__(self, key):
        if key in self.data:
            value = self.data[key]
            if isinstance(value, dict):
                nested_config = Config.__new__(Config)
                nested_config.data = value
                if type(value) == object:
                    print("Warning, item is a dict")
                return nested_config
            return value
        raise KeyError(f"Key not found: {key}")

    def consoleColourFormatter(self, colours, console_config):
        if not colours:
            colours = {
                "DEBUG": "blue",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "light_red",
                "CRITICAL": "red"
            }
        format = console_config.get("format")
        date_format = console_config.get("date_format")
        return colorlog.ColoredFormatter(
            fmt= '%(log_color)s' + format, 
            datefmt=date_format, 
            log_colors=colours,
            reset=True
        )
    
    def set_up_logger(self):
        """Set up the logging system based on the loaded configuration."""
        log_config = self.data.get("logging_config", {})
        console_config = log_config.get("console_output", {})
        file_config = log_config.get("file_output", {})

        # Create logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)  # Capture all levels; handlers will filter

        # Console logging
        if console_config.get("enabled", False):
            colours = console_config.get("colour", {})
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, console_config.get("level", "INFO").upper()))
            console_formatter = self.consoleColourFormatter(colours, console_config)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # File logging
        if file_config.get("enabled", False):
            log_dir = file_config.get("log_dir", "logs")
            log_file = os.path.join(log_dir, file_config.get("filename", "app.log"))
            os.makedirs(log_dir, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=file_config.get("max_bytes", 10485760),
                backupCount=file_config.get("backup_count", 5),
            )
            file_handler.setLevel(getattr(logging, file_config.get("level", "WARNING").upper()))
            file_formatter = logging.Formatter(file_config.get("format"), file_config.get("date_format"))
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
