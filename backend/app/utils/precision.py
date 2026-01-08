"""
TradeEdge Pro - Precision Utilities
Decimal-based calculations for monetary accuracy.

Avoids floating-point errors in price and P&L calculations.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union

# Precision settings
PRICE_PRECISION = 2      # 2 decimal places for INR prices
PNL_PRECISION = 2        # 2 decimal places for P&L
PERCENT_PRECISION = 2    # 2 decimal places for percentages
QUANTITY_PRECISION = 0   # Whole numbers for shares


def to_decimal(value: Union[float, int, str, Decimal], precision: int = PRICE_PRECISION) -> Decimal:
    """
    Convert any numeric value to Decimal with specified precision.
    
    Args:
        value: The value to convert
        precision: Number of decimal places (default: 2)
    
    Returns:
        Decimal with proper rounding
    """
    if value is None:
        return Decimal("0")
    
    try:
        dec = Decimal(str(value))
        quantizer = Decimal(10) ** -precision
        return dec.quantize(quantizer, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def to_float(value: Decimal, precision: int = PRICE_PRECISION) -> float:
    """Convert Decimal back to float for JSON serialization"""
    return float(round(value, precision))


def calculate_pnl(
    entry_price: Union[float, Decimal],
    exit_price: Union[float, Decimal],
    quantity: int
) -> Decimal:
    """
    Calculate P&L with Decimal precision.
    
    Args:
        entry_price: Entry price per share
        exit_price: Exit price per share
        quantity: Number of shares
    
    Returns:
        Net P&L as Decimal
    """
    entry = to_decimal(entry_price)
    exit_p = to_decimal(exit_price)
    return to_decimal((exit_p - entry) * quantity, PNL_PRECISION)


def calculate_pnl_pct(
    entry_price: Union[float, Decimal],
    exit_price: Union[float, Decimal]
) -> Decimal:
    """
    Calculate P&L percentage with Decimal precision.
    
    Returns:
        P&L percentage (e.g., 5.25 for 5.25%)
    """
    entry = to_decimal(entry_price)
    exit_p = to_decimal(exit_price)
    
    if entry == 0:
        return Decimal("0")
    
    pnl_pct = ((exit_p - entry) / entry) * 100
    return to_decimal(pnl_pct, PERCENT_PRECISION)


def calculate_position_value(price: Union[float, Decimal], quantity: int) -> Decimal:
    """Calculate total position value"""
    return to_decimal(to_decimal(price) * quantity, PNL_PRECISION)


def calculate_risk_amount(
    entry: Union[float, Decimal],
    stop_loss: Union[float, Decimal],
    quantity: int
) -> Decimal:
    """Calculate risk amount (potential loss if SL hit)"""
    entry_d = to_decimal(entry)
    sl_d = to_decimal(stop_loss)
    return to_decimal(abs(entry_d - sl_d) * quantity, PNL_PRECISION)


def calculate_shares(
    capital: Union[float, Decimal],
    risk_percent: Union[float, Decimal],
    entry: Union[float, Decimal],
    stop_loss: Union[float, Decimal]
) -> int:
    """
    Calculate number of shares based on risk management.
    
    Args:
        capital: Total capital
        risk_percent: Risk per trade (e.g., 1.0 for 1%)
        entry: Entry price
        stop_loss: Stop loss price
    
    Returns:
        Number of shares (rounded down)
    """
    cap = to_decimal(capital)
    risk_pct = to_decimal(risk_percent, PERCENT_PRECISION)
    entry_d = to_decimal(entry)
    sl_d = to_decimal(stop_loss)
    
    risk_amount = cap * (risk_pct / 100)
    sl_distance = abs(entry_d - sl_d)
    
    if sl_distance == 0:
        return 0
    
    shares = risk_amount / sl_distance
    return int(shares)  # Round down for safety


def validate_price(price: Union[float, Decimal], field_name: str = "price") -> Decimal:
    """
    Validate and convert price to Decimal.
    
    Raises:
        ValueError: If price is invalid
    """
    dec = to_decimal(price)
    
    if dec <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    
    if dec > 1000000:  # Max 10 lakh per share (reasonable for Indian markets)
        raise ValueError(f"{field_name} exceeds maximum allowed value")
    
    return dec


def validate_quantity(quantity: int) -> int:
    """
    Validate quantity.
    
    Raises:
        ValueError: If quantity is invalid
    """
    if not isinstance(quantity, int):
        quantity = int(quantity)
    
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")
    
    if quantity > 1000000:
        raise ValueError("Quantity exceeds maximum allowed value")
    
    return quantity
