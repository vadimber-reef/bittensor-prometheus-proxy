import gzip

import requests
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

# Headers that describe the encoding of the original request body and must be
# stripped when the proxy re-encodes or re-serialises the body before forwarding.
_REQUEST_HEADERS_TO_STRIP = frozenset(["content-encoding"])


def decompress_body(data: bytes, headers) -> bytes:
    encoding = headers.get("Content-Encoding", "")
    if any(e.strip().lower() in ("gzip", "x-gzip") for e in encoding.split(",")):
        return gzip.decompress(data)
    return data


def build_forwarded_request_headers(request_headers) -> dict:
    return {k: v for k, v in request_headers.items() if k.lower() not in _REQUEST_HEADERS_TO_STRIP}


def build_forwarded_response(response):
    from django.http import HttpResponse

    return HttpResponse(
        status=response.status_code,
        headers={k: v for k, v in response.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS},
        content=response.content,
    )


def build_bittensor_outbound_headers(data: bytes, hotkey, netuid: int) -> dict[str, str]:
    """Return Bittensor auth headers for an outbound proxy request."""
    return {
        "Bittensor-Hotkey": hotkey.ss58_address,
        "Bittensor-Netuid": str(netuid),
        "Bittensor-Signature": hotkey.sign(data).hex(),
    }
