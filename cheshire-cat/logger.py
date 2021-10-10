import traceback
import os

data_path = os.path.join(os.path.dirname(__file__), "../data")

extension = {
    "log": '.hdf5',
    "param": '.pickle',
    "plot": '.pdf',
    "image": '.jpg',
    "video": '.mp4',
    "csv": '.csv'
}


def write_data_to_hdf5(df, file_name="test", write_mode="w"):
    """
    Write financial dataframe to a HDF5 file.

    Args:
        df: dataframe
        file_name: name of the file where to save data
        write_mode: "w": write | "a": append

    Returns:
        None
    """
    filepath = log_pather(file_name)

    try:
        df.to_hdf(filepath, key='df', mode=write_mode)

    except PermissionError:
        traceback.print_exc()


def log_pather(file_name=None):
    """
    Return the path where to save the logs.

    Args:
        file_name: name of the log file

    Returns:
        path, the path created
    """
    path = os.path.join(data_path, 'logs')
    path = pather(path)
    if not file_name:
        return path

    if file_name.find('.') == -1:
        file_name += extension['log']
    return os.path.join(path, file_name)


def pather(path):
    """
    Create the path if it does not exist yet.

    Args:
        path: path to create

    Returns:
        path, the path that was created
    """
    if not os.path.exists(path):
        os.makedirs(path)
    path = path + '/'
    if not os.path.exists(path):
        os.makedirs(path)
    return path
