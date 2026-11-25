"""Constants and topic helpers."""
from uuid import UUID

DOMAIN = "st_local_bridge"
PREFIX = "st/local"
KINDS = ("switch", "motion", "contact", "moisture", "presence", "cover")

def device_key(value: str) -> str:
    return str(UUID(value.strip()))

def topic(key: str, suffix: str) -> str:
    return f"{PREFIX}/{device_key(key)}/{suffix}"

def parse_state(payload: str) -> bool | None:
    return {"on": True, "off": False}.get(payload)

