from http import HTTPStatus

import bittensor
import structlog
from django.conf import settings
from django.http import HttpResponse

from project.core.models import Validator

logger = structlog.getLogger(__name__)


def validate_bittensor_request(request, data: bytes) -> tuple[str, int] | HttpResponse:
    """
    Validate Bittensor auth headers on an inbound proxy request.

    Returns (ss58_address, netuid) on success, or an HttpResponse on failure:
      400  missing headers (hotkey, signature, or netuid)
      400  non-integer netuid header
      403  netuid not in settings.BITTENSOR_NETUIDS
      403  hotkey not an active validator for that netuid
      400  bad signature
    """
    ss58_address = request.headers.get("Bittensor-Hotkey")
    signature = request.headers.get("Bittensor-Signature")
    netuid_raw = request.headers.get("Bittensor-Netuid")

    if not ss58_address or not signature or not netuid_raw:
        msg = "Missing required headers."
        logger.debug(msg)
        return HttpResponse(status=HTTPStatus.BAD_REQUEST, content=msg.encode())

    try:
        netuid = int(netuid_raw)
    except ValueError:
        msg = "Invalid Bittensor-Netuid header."
        logger.debug(msg)
        return HttpResponse(status=HTTPStatus.BAD_REQUEST, content=msg.encode())

    if netuid not in settings.BITTENSOR_NETUIDS:
        msg = f"Netuid not supported: {netuid}"
        logger.debug(msg)
        return HttpResponse(status=HTTPStatus.FORBIDDEN, content=msg.encode())

    if not Validator.objects.filter(active=True, netuid=netuid, public_key=ss58_address).exists():
        msg = "Validator not active."
        logger.debug(msg)
        return HttpResponse(status=HTTPStatus.FORBIDDEN, content=msg.encode())

    sender_keypair = bittensor.Keypair(ss58_address)
    try:
        verified = sender_keypair.verify(data, "0x" + signature)
    except ValueError:
        verified = False
    if not verified:
        msg = "Bad signature."
        logger.debug(msg)
        return HttpResponse(status=HTTPStatus.BAD_REQUEST, content=msg.encode())

    return ss58_address, netuid
