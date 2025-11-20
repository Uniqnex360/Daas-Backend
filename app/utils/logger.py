import logging
from logging.handlers import RotatingFileHandler
import os
LOG_DIR='logs'
os.makedirs(LOG_DIR,exist_ok=True)
def get_loggers(name:str)->logging.Logger:
    logger=logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter=logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    ch=logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    fh=RotatingFileHandler(f"{LOG_DIR}/{name}.log",maxBytes=5_000_000,backupCount=5)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger
    