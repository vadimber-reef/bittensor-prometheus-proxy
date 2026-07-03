import time

import structlog
from celery import Task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.cache import cache

from project.celery import app
from project.core.contact import subtensor_contact
from project.core.models import Validator

logger = structlog.wrap_logger(get_task_logger(__name__))

LOCK_KEY = "fetch_validators_lock"
LOCK_TIMEOUT = getattr(settings, "CELERY_TASK_TIME_LIMIT", 300) + 60  # must outlive the hard kill
FAILURE_ERROR_THRESHOLD = 2 * 3600  # 2 hours in seconds
LAST_SUCCESS_TTL = 7 * 24 * 3600  # 7 days; refreshed every 5 min on success, guards against stale netuid reuse


def last_success_key(netuid: int) -> str:
    return f"fetch_validators_last_success_{netuid}"


def send_to_dead_letter_queue(task: Task, exc, task_id, args, kwargs, einfo):
    """Hook to put a task into dead letter queue when it fails."""
    if task.app.conf.task_always_eager:
        return  # do not run failed task again in eager mode

    logger.warning(
        "Sending failed task to dead letter queue",
        task=task,
        exc=exc,
        task_id=task_id,
        args=args,
        kwargs=kwargs,
        einfo=einfo,
    )
    task.apply_async(args=args, kwargs=kwargs, queue="dead_letter")


def _log_failure(exc: Exception, netuid: int) -> None:
    last_success = cache.get(last_success_key(netuid))
    if last_success is None or time.time() - last_success > FAILURE_ERROR_THRESHOLD:
        logger.error("fetch_validators has been failing for more than 2 hours", netuid=netuid, exc_info=exc)
    else:
        logger.info("fetch_validators failed, will retry", netuid=netuid, exc_info=exc)


@app.task
def fetch_validators():
    if not cache.add(LOCK_KEY, 1, timeout=LOCK_TIMEOUT):
        logger.info("fetch_validators skipped, another worker holds the lock")
        return

    try:
        _fetch_validators()
    finally:
        cache.delete(LOCK_KEY)


def _fetch_validators():
    contact = subtensor_contact()
    keys_by_netuid: dict[int, set[str]] = {}
    for netuid in settings.BITTENSOR_NETUIDS:
        try:
            keys_by_netuid[netuid] = set(contact.get_validator_hotkeys(netuid))
        except Exception as exc:
            _log_failure(exc, netuid)

    for netuid, validator_keys in keys_by_netuid.items():
        debug_keys = set(
            Validator.objects.filter(netuid=netuid, debug=True, active=True).values_list("public_key", flat=True)
        )
        validator_keys |= debug_keys

        to_activate: list[Validator] = []
        to_deactivate: list[Validator] = []
        to_create: list[Validator] = []

        for validator in Validator.objects.filter(netuid=netuid):
            if validator.public_key in validator_keys:
                validator.active = True
                to_activate.append(validator)
                validator_keys.discard(validator.public_key)
            elif not validator.debug:
                validator.active = False
                to_deactivate.append(validator)

        to_create = [Validator(public_key=key, netuid=netuid, active=True) for key in validator_keys]

        Validator.objects.bulk_create(to_create)
        Validator.objects.bulk_update(to_activate + to_deactivate, ["active"])
        cache.set(last_success_key(netuid), time.time(), timeout=LAST_SUCCESS_TTL)
        logger.info(
            "Fetched validators for netuid",
            netuid=netuid,
            activated=len(to_activate),
            deactivated=len(to_deactivate),
            created=len(to_create),
        )
