from datetime import datetime


def time2str():
    """
    Convert current time to string in the form Y-m-d-H-M-S.

    Returns:
        time_string, a string of the current time
    """
    time_now = datetime.now()
    time_string = time_now.strftime("%Y-%m-%d-%H-%M-%S")
    return time_string
