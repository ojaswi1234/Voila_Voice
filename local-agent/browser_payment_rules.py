"""
browser_payment_rules.py — Dedicated payment guardrail heuristics for browser automation.
Denies checkout completion, card/CVV/bank entry, and payment CTA clicks by default.
"""

import re
from typing import Any, Tuple

PAYMENT_URL_PATTERNS = [
    "checkout",
    "/cart/checkout",
    "/payment",
    "/billing",
    "/pay/",
    "placeorder",
    "stripe.com",
    "paypal.com",
    "razorpay",
    "paytm",
    "squareup",
    "adyen",
    "braintree",
    "checkout.shopify",
    "payments.amazon",
    "buy.google",
    "apple.com/shop/buy",
]

PAYMENT_CTA_PATTERNS = [
    "pay now",
    "place order",
    "complete purchase",
    "confirm payment",
    "buy now",
    "pay with",
    "submit payment",
    "authorize payment",
    "add card and pay",
    "confirm order and pay",
]

PAYMENT_FIELD_PATTERNS = [
    "card number",
    "cardnumber",
    "cc-number",
    "pan",
    "cvv",
    "cvc",
    "cid",
    "security code",
    "expiry",
    "exp-date",
    "cc-exp",
    "iban",
    "routing number",
    "account number",
]

PAN_REGEX = re.compile(r"\b\d{13,19}\b")
FORMATTED_PAN_REGEX = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def is_payment_url(url: str) -> Tuple[bool, str]:
    """Check if URL matches any payment or checkout destination."""
    if not url:
        return False, ""
    u_lower = url.lower()
    for pat in PAYMENT_URL_PATTERNS:
        if pat in u_lower:
            return True, pat
    return False, ""


def is_payment_cta(text: str) -> Tuple[bool, str]:
    """Check if button text, aria-label, or selector indicates payment finalization."""
    if not text:
        return False, ""
    t_lower = text.lower()
    for pat in PAYMENT_CTA_PATTERNS:
        if pat in t_lower:
            return True, pat
    return False, ""


def is_payment_field(field_identifier: str, on_payment_url: bool = False) -> Tuple[bool, str]:
    """Check if input name, id, placeholder, label, or selector is a payment data field."""
    if not field_identifier:
        return False, ""
    f_lower = field_identifier.lower()
    for pat in PAYMENT_FIELD_PATTERNS:
        if pat in f_lower:
            return True, pat
    if on_payment_url:
        for otp_pat in ("otp", "one time password", "verification code"):
            if otp_pat in f_lower:
                return True, f"payment_{otp_pat}"
    return False, ""


def is_pan_number(value: str) -> bool:
    """Check if string contains a credit card or PAN number (13 to 19 digits)."""
    if not value or not isinstance(value, str):
        return False
    digits = re.sub(r"\D", "", value)
    return 13 <= len(digits) <= 19 and PAN_REGEX.search(value) is not None


def mask_pan(text: str) -> str:
    """Mask 13-19 digit card numbers as ************1234."""
    if not isinstance(text, str):
        return text

    def _replace_pan(m):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19:
            return "*" * (len(digits) - 4) + digits[-4:]
        return raw

    return FORMATTED_PAN_REGEX.sub(_replace_pan, text)


def mask_sensitive(obj: Any) -> Any:
    """Recursively mask sensitive PAN data in dicts, lists, and strings."""
    if isinstance(obj, str):
        return mask_pan(obj)
    elif isinstance(obj, dict):
        return {k: mask_sensitive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [mask_sensitive(x) for x in obj]
    return obj


def is_payment_eval(script: str) -> Tuple[bool, str]:
    """Check if javascript evaluation attempts to write to payment fields."""
    if not script or not isinstance(script, str):
        return False, ""
    s_lower = script.lower()
    if ("value" in s_lower or "innertext" in s_lower or "innerhtml" in s_lower) and any(
        kw in s_lower for kw in ("card", "cvv", "cvc", "pan", "iban", "routing")
    ):
        return True, "eval_payment_field_setter"
    if PAN_REGEX.search(script):
        return True, "eval_pan_injection"
    return False, ""
