import os
from http import HTTPStatus

import pytest
from django.test import override_settings
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

from project.core.contact.tempo import TempoContact

pytestmark = pytest.mark.integration

TEMPO_URL = "http://localhost:4319"


def _make_traces(
    hotkey: str = "5TestHotkey",
    netuid: str = "12",
    span_count: int = 1,
    resource_span_count: int = 1,
) -> bytes:
    req = trace_service_pb2.ExportTraceServiceRequest()
    for _ in range(resource_span_count):
        rs = req.resource_spans.add()
        for key, value in [("hotkey", hotkey), ("netuid", netuid)]:
            kv = rs.resource.attributes.add()
            kv.key = key
            kv.value.string_value = value
        ss = rs.scope_spans.add()
        for i in range(span_count):
            span = ss.spans.add()
            span.name = f"integration-test-span-{i}"
            span.trace_id = os.urandom(16)  # 128-bit required by Tempo
            span.span_id = os.urandom(8)  # 64-bit
    return req.SerializeToString()


@pytest.fixture
def contact():
    return TempoContact()


@override_settings(UPSTREAM_TEMPO_URL=TEMPO_URL)
def test_push_valid_traces_returns_2xx(contact):
    response = contact.push_traces(_make_traces(), content_type="application/x-protobuf")
    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)


@override_settings(UPSTREAM_TEMPO_URL=TEMPO_URL)
def test_push_empty_request_accepted(contact):
    req = trace_service_pb2.ExportTraceServiceRequest()
    response = contact.push_traces(req.SerializeToString(), content_type="application/x-protobuf")
    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)


@override_settings(UPSTREAM_TEMPO_URL=TEMPO_URL)
def test_push_multiple_spans(contact):
    response = contact.push_traces(_make_traces(span_count=10), content_type="application/x-protobuf")
    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)


@override_settings(UPSTREAM_TEMPO_URL=TEMPO_URL)
def test_push_multiple_resource_spans(contact):
    response = contact.push_traces(_make_traces(resource_span_count=3), content_type="application/x-protobuf")
    assert response.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)


@override_settings(UPSTREAM_TEMPO_URL=TEMPO_URL)
def test_push_invalid_protobuf_returns_4xx(contact):
    response = contact.push_traces(b"not-valid-protobuf", content_type="application/x-protobuf")
    assert HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
