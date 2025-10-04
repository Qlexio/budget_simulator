from decimal import Decimal as _Decimal


def quantize_amount(value):
    return value.quantize(_Decimal("0.01"))

def to_decimal(value, precision: str = "0.01"):
    return _Decimal(str(value)).quantize(_Decimal(precision))