from decimal import Decimal as _Decimal


def quantize_amount(value) -> _Decimal:
    return value.quantize(_Decimal("0.01"))

def to_decimal(value, precision: str = "0.01") -> _Decimal:
    return _Decimal(str(value)).quantize(_Decimal(precision))