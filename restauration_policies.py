import abc
import numpy as np
import logging


class RoutingPolicy(abc.ABC):

    def __init__(self):
        self.env = None
        self.name = None

    @abc.abstractmethod
    def restore(self, service):
        pass

