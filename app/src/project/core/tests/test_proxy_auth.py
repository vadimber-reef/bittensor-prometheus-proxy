from http import HTTPStatus

import pytest
from django.http import HttpResponse
from django.test import override_settings

from project.core.models import Validator
from project.core.proxy_auth import validate_bittensor_request


def _signed_request(rf, data=b"test", hotkey=None, netuid=None, signature=None):
    headers = {}
    if hotkey:
        headers["HTTP_BITTENSOR_HOTKEY"] = hotkey
    if netuid is not None:
        headers["HTTP_BITTENSOR_NETUID"] = str(netuid)
    if signature is not None:
        headers["HTTP_BITTENSOR_SIGNATURE"] = signature
    return rf.post("/", data=data, content_type="application/octet-stream", **headers)


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_missing_headers_returns_400(rf):
    request = rf.post("/", content_type="application/octet-stream")
    result = validate_bittensor_request(request, b"data")
    assert isinstance(result, HttpResponse)
    assert result.status_code == HTTPStatus.BAD_REQUEST
    assert b"Missing required headers" in result.content


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_invalid_netuid_returns_400(rf, keypair):
    data = b"test"
    request = _signed_request(
        rf, data=data, hotkey=keypair.ss58_address, netuid="not-a-number", signature=keypair.sign(data).hex()
    )
    result = validate_bittensor_request(request, data)
    assert isinstance(result, HttpResponse)
    assert result.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_unsupported_netuid_returns_403(rf, keypair):
    data = b"test"
    request = _signed_request(rf, data=data, hotkey=keypair.ss58_address, netuid=99, signature=keypair.sign(data).hex())
    result = validate_bittensor_request(request, data)
    assert isinstance(result, HttpResponse)
    assert result.status_code == HTTPStatus.FORBIDDEN
    assert b"Netuid not supported" in result.content


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_inactive_validator_returns_403(rf, keypair):
    data = b"test"
    # no Validator row created — hotkey is unknown
    request = _signed_request(rf, data=data, hotkey=keypair.ss58_address, netuid=12, signature=keypair.sign(data).hex())
    result = validate_bittensor_request(request, data)
    assert isinstance(result, HttpResponse)
    assert result.status_code == HTTPStatus.FORBIDDEN
    assert b"Validator not active" in result.content


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_bad_signature_returns_400(rf, keypair):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = b"test"
    request = _signed_request(
        rf,
        data=data,
        hotkey=keypair.ss58_address,
        netuid=12,
        signature=keypair.sign(b"different-data").hex(),  # wrong signature
    )
    result = validate_bittensor_request(request, data)
    assert isinstance(result, HttpResponse)
    assert result.status_code == HTTPStatus.BAD_REQUEST
    assert b"Bad signature" in result.content


@pytest.mark.django_db
@override_settings(BITTENSOR_NETUIDS=[12])
def test_valid_request_returns_address_and_netuid(rf, keypair):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = b"test"
    request = _signed_request(rf, data=data, hotkey=keypair.ss58_address, netuid=12, signature=keypair.sign(data).hex())
    result = validate_bittensor_request(request, data)
    assert result == (keypair.ss58_address, 12)
