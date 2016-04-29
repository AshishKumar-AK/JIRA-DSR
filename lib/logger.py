import logging
import os
from colorama import Fore, Style
from colorama import init
from builtins import print


class InteractiveLogger(logging.getLoggerClass()):
    """
    Custom wrapper class on standard python logging
    module to enable terminal log output with color formats
    """
    def __init__(self, logdir, logfile, logformat=None, datefmt=None, logfilemode='w',
                 verbose=False, interactive=False):
        init(autoreset=True)
        self.logdir = logdir
        self.logfile = logfile
        self.interactive = interactive
        self.verbose = verbose
        self.interactive_format = '{level:<8s} {msg:<1s}'

        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir)

        if self.verbose:
            self.level = logging.DEBUG
        else:
            self.level = logging.INFO

        if logformat:
            self.format = logformat
        else:
            self.format = '%(asctime)s %(levelname)-8s %(message)s'

        if datefmt:
            self.datefmt = datefmt
        else:
            self.datefmt = '%Y-%m-%d %H:%M:%S'

        logging.basicConfig(level=self.level,
                            format=self.format,
                            datefmt=self.datefmt,
                            filename=os.path.join(self.logdir, self.logfile),
                            filemode=logfilemode)

    def get_logfile(self):
        return os.path.join(self.logdir, self.logfile)

    def error(self, log):
        if self.interactive:
            msg = Fore.RED + Style.BRIGHT + self.interactive_format.format(level="ERROR",
                                                                           msg=log)
            print(msg)
        self.root.error(log)

    def warning(self, log):
        if self.interactive:
            msg = Fore.YELLOW + Style.BRIGHT + self.interactive_format.format(level="WARN",
                                                                              msg=log)
            print(msg)
        self.root.warning(log)

    def info(self, log):
        if self.interactive:
            msg = Fore.WHITE + Style.BRIGHT + self.interactive_format.format(level="INFO",
                                                                             msg=log)
            print(msg)
        self.root.info(log)

    def debug(self, log):
        if self.verbose and self.interactive:
            msg = Fore.GREEN + Style.BRIGHT + self.interactive_format.format(level="DEBUG",
                                                                             msg=log)
            print(msg)
        self.root.debug(log)