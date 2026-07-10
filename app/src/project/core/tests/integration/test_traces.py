import os
import time
from http import HTTPStatus

import pytest
import requests
from django.test import override_settings
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

from project.core.models import Validator

pytestmark = pytest.mark.integration

TEMPO_URL = "http://localhost:4319"


def _make_payload() -> bytes:
    req = trace_service_pb2.ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    ss = rs.scope_spans.add()
    span = ss.spans.add()
    span.name = "chain-integration-test"
    span.trace_id = os.urandom(16)
    span.span_id = os.urandom(8)
    span.start_time_unix_nano = time.time_ns()
    span.end_time_unix_nano = time.time_ns() + 1_000_000_000
    return req.SerializeToString()


@pytest.mark.django_db(transaction=True)
def test_traces_outbound_to_inbound_to_tempo(live_server, keypair, mock_wallet):
    Validator.objects.create(public_key=keypair.ss58_address, netuid=12, active=True, debug=True)

    with override_settings(
        CENTRAL_TEMPO_PROXY_URL=live_server.url,
        UPSTREAM_TEMPO_URL=TEMPO_URL,
        BITTENSOR_NETUID=12,
        BITTENSOR_NETUIDS=[12],
        BITTENSOR_WALLET=mock_wallet,
    ):
        response = requests.post(
            f"{live_server.url}/traces/outbound",
            data=_make_payload(),
            headers={"Content-Type": "application/x-protobuf"},
            timeout=30,
        )

    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)
