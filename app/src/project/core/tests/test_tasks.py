import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from project.core.models import Validator
from project.core.tasks import LOCK_KEY, fetch_validators, last_success_key


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def patched_subtensor_contact(mock_contact):
    with patch("project.core.tasks.subtensor_contact", return_value=mock_contact):
        yield


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__creates_new_validators(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", ["5Alice", "5Bob"])

    fetch_validators()

    assert Validator.objects.filter(public_key="5Alice", netuid=12, active=True).exists()
    assert Validator.objects.filter(public_key="5Bob", netuid=12, active=True).exists()
    assert mock_contact.calls["get_validator_hotkeys"] == [(12,)]


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__deactivates_removed_validators(mock_contact):
    Validator.objects.create(public_key="5OldKey", netuid=12, active=True, debug=False)
    mock_contact.add_behavior("get_validator_hotkeys", [])

    fetch_validators()

    assert not Validator.objects.get(public_key="5OldKey", netuid=12).active


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__preserves_debug_validators(mock_contact):
    Validator.objects.create(public_key="5Debug", netuid=12, active=True, debug=True)
    mock_contact.add_behavior("get_validator_hotkeys", [])

    fetch_validators()

    assert Validator.objects.get(public_key="5Debug", netuid=12).active


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12, 22])
def test_fetch_validators__supports_multiple_netuids(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", ["5Alice"])
    mock_contact.add_behavior("get_validator_hotkeys", ["5Bob"])

    fetch_validators()

    assert Validator.objects.filter(public_key="5Alice", netuid=12, active=True).exists()
    assert Validator.objects.filter(public_key="5Bob", netuid=22, active=True).exists()
    assert not Validator.objects.filter(public_key="5Alice", netuid=22).exists()
    assert mock_contact.calls["get_validator_hotkeys"] == [(12,), (22,)]


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__sets_last_success_on_ok(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", [])

    before = time.time()
    fetch_validators()
    after = time.time()

    ts = cache.get(last_success_key(12))
    assert ts is not None
    assert before <= ts <= after


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
@patch("project.core.tasks.logger")
def test_fetch_validators__logs_info_on_recent_failure(mock_logger, mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))
    cache.set(last_success_key(12), time.time() - 3600, timeout=None)

    fetch_validators()

    mock_logger.info.assert_called_once()
    mock_logger.error.assert_not_called()


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
@patch("project.core.tasks.logger")
def test_fetch_validators__logs_error_after_2h_failure(mock_logger, mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))
    cache.set(last_success_key(12), time.time() - 3 * 3600, timeout=None)

    fetch_validators()

    mock_logger.error.assert_called_once()
    mock_logger.info.assert_not_called()


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
@patch("project.core.tasks.logger")
def test_fetch_validators__logs_error_when_never_succeeded(mock_logger, mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))

    fetch_validators()

    mock_logger.error.assert_called_once()


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12, 22])
def test_fetch_validators__partial_failure_updates_successful_netuids(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", ["5Alice"])
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))

    fetch_validators()

    assert Validator.objects.filter(public_key="5Alice", netuid=12, active=True).exists()
    ts = cache.get(last_success_key(12))
    assert ts is not None


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__all_fail_does_not_update_last_success(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))

    fetch_validators()

    assert cache.get(last_success_key(12)) is None


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
@patch("project.core.tasks.logger")
def test_fetch_validators__skips_when_lock_held(mock_logger, mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", ["5Alice"])
    cache.add(LOCK_KEY, 1, timeout=290)

    fetch_validators()

    mock_logger.info.assert_called_once_with("fetch_validators skipped, another worker holds the lock")
    assert not Validator.objects.filter(public_key="5Alice").exists()


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__releases_lock_after_success(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", [])

    fetch_validators()

    assert cache.get(LOCK_KEY) is None


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_fetch_validators__releases_lock_after_failure(mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))

    fetch_validators()

    assert cache.get(LOCK_KEY) is None


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12, 22])
@patch("project.core.tasks.logger")
def test_fetch_validators__tracks_last_success_per_netuid(mock_logger, mock_contact):
    mock_contact.add_behavior("get_validator_hotkeys", ["5Alice"])
    mock_contact.add_behavior("get_validator_hotkeys", Exception("rpc error"))

    fetch_validators()

    assert cache.get(last_success_key(12)) is not None
    assert cache.get(last_success_key(22)) is None  # not updated on failure
    mock_logger.info.assert_called_once()   # netuid 12 success log
    mock_logger.error.assert_called_once()  # netuid 22: no prior success → error
