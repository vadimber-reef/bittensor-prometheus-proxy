from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from project.core.models import Validator


@pytest.mark.django_db
@override_settings(UPSTREAM_PROMETHEUS_URL="http://upstream", BITTENSOR_NETUIDS=[12])
def test_missing_netuid_header(client, keypair, make_write_request_body):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = make_write_request_body(keypair.ss58_address)
    response = client.post(
        "/prometheus/inbound",
        data=data,
        content_type="application/octet-stream",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
        # no HTTP_BITTENSOR_NETUID
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert b"Missing required headers" in response.content


@pytest.mark.django_db
@override_settings(UPSTREAM_PROMETHEUS_URL="http://upstream", BITTENSOR_NETUIDS=[12])
def test_netuid_not_in_allowed_list(client, keypair, make_write_request_body):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = make_write_request_body(keypair.ss58_address)
    response = client.post(
        "/prometheus/inbound",
        data=data,
        content_type="application/octet-stream",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
        HTTP_BITTENSOR_NETUID="99",  # not in [12]
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert b"Netuid not supported" in response.content


@pytest.mark.django_db
@override_settings(UPSTREAM_PROMETHEUS_URL="http://upstream", BITTENSOR_NETUIDS=[12])
def test_hotkey_not_active_for_netuid(client, keypair, make_write_request_body):
    # active on netuid 22, NOT 12
    Validator.objects.create(public_key=keypair.ss58_address, netuid=22, active=True)
    data = make_write_request_body(keypair.ss58_address)
    response = client.post(
        "/prometheus/inbound",
        data=data,
        content_type="application/octet-stream",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
        HTTP_BITTENSOR_NETUID="12",
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert b"Validator not active" in response.content


@pytest.mark.django_db
@override_settings(UPSTREAM_PROMETHEUS_URL="http://upstream", BITTENSOR_NETUIDS=[12])
@patch("project.core.views.prometheus.session")
def test_valid_request_forwarded(mock_session, client, keypair, make_write_request_body):
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NO_CONTENT
    mock_response.content = b""
    mock_response.headers = {}
    mock_session.post.return_value = mock_response

    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = make_write_request_body(keypair.ss58_address)
    response = client.post(
        "/prometheus/inbound",
        data=data,
        content_type="application/octet-stream",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
        HTTP_BITTENSOR_NETUID="12",
    )
    assert response.status_code == HTTPStatus.NO_CONTENT
    mock_session.post.assert_called_once()
