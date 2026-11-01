import copy

import pytest

from campus_support.config import Config
from campus_support.pipeline import generate
from campus_support.rules import Context


@pytest.fixture(scope="session")
def cfg():
    return Config(tickets=800, articles=120)          # same generator as the 5,000-ticket build, smaller scale


@pytest.fixture(scope="session")
def data(cfg):
    return generate(cfg)


@pytest.fixture(scope="session")
def ctx(data, cfg):
    return Context(data[0], cfg.as_of)


@pytest.fixture()
def tables(data):
    """Private deep copy per test so mutation tests never pollute the shared dataset."""
    return copy.deepcopy(data[0])
