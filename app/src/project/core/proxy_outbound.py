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
    ["connection", "keep-alive", "public", "proxy-authenticate", "transfer-encoding", "upgrade"]
)


def build_bittensor_outbound_headers(data: bytes, hotkey, netuid: int) -> dict[str, str]:
    """Return Bittensor auth headers for an outbound proxy request."""
    return {
        "Bittensor-Hotkey": hotkey.ss58_address,
        "Bittensor-Netuid": str(netuid),
        "Bittensor-Signature": hotkey.sign(data).hex(),
    }
