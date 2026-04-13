from typing import Any

__all__ = ["sqlite_store"]


def coerce_to_str_dict(data: dict[str, Any]) -> dict[str, str]:
    return {k: "" if v is None else str(v) for k, v in data.items()}
