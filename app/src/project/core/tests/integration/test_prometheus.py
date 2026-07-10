import time
from http import HTTPStatus

import pytest
import requests
import snappy
from django.test import override_settings

from project.core.models import Validator
from project.core.prometheus_protobuf import remote_pb2

pytestmark = pytest.mark.integration

UPSTREAM_PROMETHEUS_URL = "http://localhost:19090"


def _make_payload(hotkey: str) -> bytes:
    wr = remote_pb2.WriteRequest()
    ts = wr.timeseries.add()
    ts.labels.add(name="__name__", value="chain_integration_test_metric")
    ts.labels.add(name="hotkey", value=hotkey)
    ts.samples.add(value=1.0, timestamp=int(time.time() * 1000))
    return snappy.compress(wr.SerializeToString())


@pytest.mark.django_db(transaction=True)
def test_prometheus_outbound_to_inbound_to_upstream(live_server, keypair, mock_wallet):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True, debug=True)

    with override_settings(
        CENTRAL_PROMETHEUS_PROXY_URL=live_server.url,
        UPSTREAM_PROMETHEUS_URL=UPSTREAM_PROMETHEUS_URL,
        BITTENSOR_NETUID=12,
        BITTENSOR_NETUIDS=[12],
        BITTENSOR_WALLET=mock_wallet,
    ):
        response = requests.post(
            f"{live_server.url}/prometheus/outbound",
            data=_make_payload(keypair.ss58_address),
            headers={"Content-Type": "application/x-protobuf"},
            timeout=30,
        )

    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)
