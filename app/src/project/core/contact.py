import functools
from abc import ABC, abstractmethod

from django.conf import settings
from pylon_client.artanis import Config, PylonClient


class AbstractSubtensorContact(ABC):
    @abstractmethod
    def get_validator_hotkeys(self, netuid: int) -> list[str]: ...


class SubtensorContact(AbstractSubtensorContact):
    """Abstracts all bittensor chain reads via the pylon openaccess API."""

    def get_validator_hotkeys(self, netuid: int) -> list[str]:
        config = Config(
            address=settings.PYLON_ENDPOINT,
            open_access_token=settings.PYLON_OPEN_ACCESS_TOKEN or None,
        )
        with PylonClient(config) as client:
            response = client.v1.open_access.get_latest_validators(netuid)
        return [str(neuron.hotkey) for neuron in response.validators]


@functools.cache
def subtensor_contact() -> AbstractSubtensorContact:
    return SubtensorContact()
