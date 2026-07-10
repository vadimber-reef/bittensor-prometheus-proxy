import pytest
import snappy
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

from project.core.prometheus_protobuf import remote_pb2


@pytest.fixture
def make_write_request_body():
    def _make(hotkey: str) -> bytes:
        wr = remote_pb2.WriteRequest()
        ts = wr.timeseries.add()
        ts.labels.add(name="__name__", value="test_metric")
        ts.labels.add(name="hotkey", value=hotkey)
        ts.samples.add(value=1.0, timestamp=0)
        return snappy.compress(wr.SerializeToString())

    return _make


@pytest.fixture
def make_traces_body():
    def _make(hotkey: str | None = None) -> bytes:
        req = trace_service_pb2.ExportTraceServiceRequest()
        rs = req.resource_spans.add()
        if hotkey is not None:
            kv = rs.resource.attributes.add()
            kv.key = "hotkey"
            kv.value.string_value = hotkey
        ss = rs.scope_spans.add()
        span = ss.spans.add()
        span.name = "test-span"
        return req.SerializeToString()

    return _make
