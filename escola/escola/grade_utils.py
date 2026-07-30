from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value, ndigits=0):
    """Round like a person would (13.5 -> 14, 13.45 -> 13), unlike Python's
    built-in round() which uses banker's rounding (round-half-to-even) and
    can silently round 13.5 down to 13.
    """
    if value is None:
        return None
    quantum = Decimal(1).scaleb(-ndigits)
    result = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return int(result) if ndigits == 0 else float(result)
