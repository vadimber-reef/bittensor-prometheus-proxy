from urllib.parse import urljoin

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .prometheus_protobuf import remote_pb2

import bittensor
import requests
import structlog
import snappy
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from project.core.models import Validator
from .metrics import series_counter, metrics_counter

logger = structlog.getLogger(__name__)
retries = Retry(
    total=3,
    connect=3,
    read=3,
    redirect=3,
    backoff_factor=0.1,
    status_forcelist=(),
    raise_on_status=False,
    allowed_methods=False,  # default excludes POST; False retries all methods (safe here since Prometheus remote write is idempotent)
)

TIMEOUT = 15

session = requests.Session()
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))


@csrf_exempt
@require_POST
def prometheus_outbound_proxy(request):
    if not settings.CENTRAL_PROMETHEUS_PROXY_URL:
        msg = "CENTRAL_PROMETHEUS_PROXY_URL is not configured"
        logger.error(msg)
        return HttpResponse(status=500, content=msg.encode())
    data = request.body

    prometheus_remote_url = urljoin(settings.CENTRAL_PROMETHEUS_PROXY_URL, 'prometheus_inbound_proxy/')

    try:
        response = session.post(
            prometheus_remote_url,
            data=data,
            headers={
                'Bittensor-Signature': settings.BITTENSOR_WALLET().hotkey.sign(data).hex(),
                'Bittensor-Hotkey': settings.BITTENSOR_WALLET().hotkey.ss58_address,
                **request.headers,
            },
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        logger.info(f"Sending to central prometheus proxy failed: {e}")
        return HttpResponse(status=500, content=type(e).__name__)

    logger.debug(f"Central prometheus proxy replied with {response.status_code}, {response.content[:200]}")
    return HttpResponse(
        status=response.status_code,
        headers={k: v for k, v in response.headers.items() if k.lower() not in [
            'connection', 'keep-alive', 'public',
            'proxy-authenticate', 'transfer-encoding', 'upgrade'
        ]},
        content=response.content,
    )


@csrf_exempt
@require_POST
def prometheus_inbound_proxy(request):
    if not settings.UPSTREAM_PROMETHEUS_URL:
        msg = "UPSTREAM_PROMETHEUS_URL is not configured"
        logger.error(msg)
        return HttpResponse(status=500, content=msg.encode())

    data = request.body
    ss58_address = request.headers.get('Bittensor-Hotkey')
    signature = request.headers.get('Bittensor-Signature')
    if not ss58_address or not signature:
        msg = "Missing required headers."
        logger.debug(msg)
        return HttpResponse(status=400, content=msg)

    if ss58_address not in Validator.objects.filter(active=True).values_list('public_key', flat=True):
        msg = "Validator not active."
        logger.debug(msg)
        return HttpResponse(status=403, content=msg)

    sender_keypair = bittensor.Keypair(ss58_address)
    if not sender_keypair.verify(data, "0x" + signature):
        msg = "Bad signature."
        logger.debug(msg)
        return HttpResponse(status=400, content=msg)

    try:
        decompressed_data = snappy.uncompress(data)
    except Exception as e:
        msg = f"Failed to decompress data: {str(e)}"
        logger.debug(msg)
        return HttpResponse(msg.encode(), status=400)

    try:
        write_request = remote_pb2.WriteRequest()
        write_request.ParseFromString(decompressed_data)
    except Exception as e:
        msg = f"Failed to decode metrics: {str(e)}"
        logger.debug(msg)
        return HttpResponse(msg, status=400)

    # Now you can access the TimeSeries data in the write_request
    series_count = 0
    metrics = set()
    for ts in write_request.timeseries:
        name = "<undefined>"
        error = None
        hotkey = None

        for label in ts.labels:

            if label.name == 'hotkey':
                hotkey = label.value
                if label.value != ss58_address:
                    msg = f"Received invalid hotkey. Expected {ss58_address} got {label.value}"
                    error = HttpResponse(status=403, content=msg.encode())
            if label.name == '__name__':
                name = label.value
        if not hotkey:
            msg = f"Received no hotkey"
            error = HttpResponse(status=403, content=msg.encode())

        if error is not None:
            error.content = f"Metric: {name}. ".encode() + error.content
            logger.info(error.content.decode())
            return error
        series_count += 1
        metrics.add(name)
    series_counter.labels(ss58_address).inc(series_count)
    metrics_counter.labels(ss58_address).inc(len(metrics))

    logger.debug("%s sent %s metrics and %s series", ss58_address, len(metrics), series_count)

    prometheus_remote_url = urljoin(settings.UPSTREAM_PROMETHEUS_URL, 'api/v1/write')

    # Forward the received data with the hash in the headers
    try:
        response = session.post(
            prometheus_remote_url,
            data=data,
            headers=request.headers,
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return HttpResponse(status=500, content=type(e).__name__)

    return HttpResponse(
        headers=response.headers,
        content=response.content,
    )
