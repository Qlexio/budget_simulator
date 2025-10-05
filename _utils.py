from decimal import Decimal as _Decimal
from typing import Union


def quantize_amount(value: _Decimal) -> _Decimal:
    """_summary_

    Args:
        value (_Decimal): _description_

    Returns:
        _Decimal: _description_
    """
    return value.quantize(_Decimal("0.01"))

def to_decimal(value: Union[int, float], precision: str = "0.01") -> _Decimal:
    """_summary_

    Args:
        value (Union[int, float]): _description_
        precision (str, optional): _description_. Defaults to "0.01".

    Returns:
        _Decimal: _description_
    """
    return _Decimal(str(value)).quantize(_Decimal(precision))