from http import HTTPStatus

import pytest
from django.test import override_settings

from project.core.models import Validator


def test_not_configured_returns_500(client):
    # test settings has UPSTREAM_TEMPO_URL="" — view returns 500 immediately
    response = client.post("/traces/inbound", data=b"data", content_type="application/x-protobuf")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


@pytest.mark.django_db
@override_settings(UPSTREAM_TEMPO_URL="http://upstream-tempo", BITTENSOR_NETUIDS=[12])
def test_missing_auth_headers_returns_400(client, keypair, make_traces_body):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    response = client.post(
        "/traces/inbound",
        data=make_traces_body(hotkey=keypair.ss58_address),
        content_type="application/x-protobuf",
        # no Bittensor-* headers
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert b"Missing required headers" in response.content


@pytest.mark.django_db
@override_settings(UPSTREAM_TEMPO_URL="http://upstream-tempo", BITTENSOR_NETUIDS=[12])
def test_malformed_body_returns_400(client, keypair):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = b"not-valid-protobuf"
    response = client.post(
        "/traces/inbound",
        data=data,
        content_type="application/x-protobuf",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_NETUID="12",
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.django_db
@override_settings(UPSTREAM_TEMPO_URL="http://upstream-tempo", BITTENSOR_NETUIDS=[12])
def test_missing_hotkey_attribute_returns_403(client, keypair, make_traces_body):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = make_traces_body(hotkey=None)  # resource has no hotkey attribute
    response = client.post(
        "/traces/inbound",
        data=data,
        content_type="application/x-protobuf",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_NETUID="12",
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.django_db
@override_settings(UPSTREAM_TEMPO_URL="http://upstream-tempo", BITTENSOR_NETUIDS=[12])
def test_mismatched_hotkey_attribute_returns_403(client, keypair, make_traces_body):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True)
    data = make_traces_body(hotkey="5SomethingElse")  # attribute differs from auth header
    response = client.post(
        "/traces/inbound",
        data=data,
        content_type="application/x-protobuf",
        HTTP_BITTENSOR_HOTKEY=keypair.ss58_address,
        HTTP_BITTENSOR_NETUID="12",
        HTTP_BITTENSOR_SIGNATURE=keypair.sign(data).hex(),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
