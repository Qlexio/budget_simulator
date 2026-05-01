from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation
from typing import Union


def quantize_amount(value: _Decimal) -> _Decimal:
    """Snap a Decimal value to 2 decimal places (cents).

    Args:
        value (_Decimal): The value to quantize.

    Returns:
        _Decimal: The value rounded to the nearest cent.

    Raises:
        TypeError: If value is not a Decimal instance.
    """
    if not isinstance(value, _Decimal):
        raise TypeError(f"Expected Decimal, got {type(value).__name__}")
    return value.quantize(_Decimal("0.01"))


def to_decimal(value: Union[int, float], precision: str = "0.01") -> _Decimal:
    """Convert an int or float to a Decimal quantized to the given precision.

    Conversion goes through str() to avoid floating-point representation
    issues before rounding.

    Args:
        value (Union[int, float]): The numeric value to convert.
        precision (str, optional): Quantization string (e.g. "0.01", "0.00001").
            Defaults to "0.01".

    Returns:
        _Decimal: The value as a Decimal rounded to the requested precision.

    Raises:
        TypeError: If value is not an int or float.
        ValueError: If precision is not a valid Decimal quantizer string.
    """
    if not isinstance(value, (int, float)):
        raise TypeError(f"Expected int or float, got {type(value).__name__}")
    try:
        quantizer = _Decimal(precision)
    except _InvalidOperation:
        raise ValueError(f"Invalid precision string: {precision!r}")
    return _Decimal(str(value)).quantize(quantizer)