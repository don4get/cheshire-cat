from datetime import datetime
import re

def time2str():
    """
    Convert current time to string in the form Y-m-d-H-M-S.

    Returns:
        time_string, a string of the current time
    """
    time_now = datetime.now()
    time_string = time_now.strftime("%Y-%m-%d-%H-%M-%S")
    return time_string

def camel_to_snake(name):
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

