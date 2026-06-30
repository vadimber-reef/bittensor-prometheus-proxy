from collections.abc import Generator

import bittensor
import pytest

from project.core.tests.mock_contact import MockSubtensorContact


@pytest.fixture
def some() -> Generator[int, None, None]:
    yield 1


@pytest.fixture
def keypair():
    return bittensor.Keypair.create_from_mnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    )


@pytest.fixture
def mock_contact():
    return MockSubtensorContact()
