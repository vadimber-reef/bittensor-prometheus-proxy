import gzip

import requests
from django.http import HttpResponse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

_retries = Retry(
    total=3,
    connect=3,
    read=3,
    redirect=3,
    backoff_factor=0.1,
    status_forcelist=(),
    raise_on_status=False,
)
TIMEOUT = 15
session = requests.Session()
session.mount("http://", HTTPAdapter(max_retries=_retries))
session.mount("https://", HTTPAdapter(max_retries=_retries))

HOP_BY_HOP_HEADERS = frozenset(
    {"connection", "keep-alive", "public", "proxy-authenticate", "transfer-encoding", "upgrade"}
)

# Headers that describe the encoding and size of the body. Must be stripped whenever the body
# is decompressed or modified before forwarding, since they no longer match the actual bytes sent.
BODY_ENCODING_HEADERS = frozenset({"content-encoding", "content-length"})

# requests auto-decompresses response.content, so strip encoding metadata before forwarding.
# Django recalculates Content-Length from the actual content passed to HttpResponse.
_RESPONSE_HEADERS_TO_STRIP = HOP_BY_HOP_HEADERS | BODY_ENCODING_HEADERS


def decompress_body(data: bytes, headers) -> bytes:
    encoding = headers.get("Content-Encoding", "")
    if any(e.strip().lower() in ("gzip", "x-gzip") for e in encoding.split(",")):
        return gzip.decompress(data)
    return data


def build_forwarded_response(response):
    return HttpResponse(
        status=response.status_code,
        headers={k: v for k, v in response.headers.items() if k.lower() not in _RESPONSE_HEADERS_TO_STRIP},
        content=response.content,
    )


def build_bittensor_outbound_headers(data: bytes, hotkey, netuid: int) -> dict[str, str]:
    """Return Bittensor auth headers for an outbound proxy request."""
    return {
        "Bittensor-Hotkey": hotkey.ss58_address,
        "Bittensor-Netuid": str(netuid),
        "Bittensor-Signature": hotkey.sign(data).hex(),
    }
