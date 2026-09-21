import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from iris_engine import RegulatoryDataset, Engine

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regulatory-data")


@pytest.fixture(scope="session")
def dataset():
    return RegulatoryDataset.load(DATA_ROOT)


@pytest.fixture(scope="session")
def engine(dataset):
    return Engine(dataset)
