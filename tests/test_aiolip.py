#!/usr/bin/env python

"""Tests for `aiolip` package."""

import pytest

from aiolip import LIP


@pytest.fixture
def response():
    """Sample pytest fixture.

    See more at: http://doc.pytest.org/en/latest/fixture.html
    """
    # import requests
    # return requests.get('https://github.com/audreyr/cookiecutter-pypackage')


def test_create(response):
    """Test to create the object."""
    LIP()
