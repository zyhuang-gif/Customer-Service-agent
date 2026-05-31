from datetime import datetime


def _gen(prefix: str) -> str:
    return f"{prefix}{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]}"


def new_refund_id() -> str:
    return _gen("RF")


def new_ticket_id() -> str:
    return _gen("TK")


def new_coupon_id() -> str:
    return _gen("CP")
