from decimal import Decimal as _Decimal


def quantize_amount(value):
    return value.quantize(_Decimal("0.01"))

