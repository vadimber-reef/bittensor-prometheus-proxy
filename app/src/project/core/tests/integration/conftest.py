import pytest


@pytest.fixture
def mock_wallet(keypair):
    # Returns the class itself (not an instance) — settings.BITTENSOR_WALLET is called as a
    # factory, so the class acts as the callable and each call returns a new instance.
    class MockWallet:
        hotkey = keypair

    return MockWallet
