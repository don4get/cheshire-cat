from utils import time2str


class Param:
    """
    Class containing the parameters.
    """

    def __init__(self):

        self.exp_name = time2str()
        self.n_tickers = 2000
        self.n_processes = 32
