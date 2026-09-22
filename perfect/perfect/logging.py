import logging


def getLogger(name):
    if name in logging.root.manager.loggerDict:
        return logging.getLogger(name)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(module)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger
