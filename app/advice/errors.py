"""Errores propios del motor de consejos."""


class AdviceError(Exception):
    """Error base del motor de consejos."""


class OutOfRangeError(AdviceError):
    """La fecha pedida no está dentro del pronóstico disponible."""


class InvalidAdviceRequest(AdviceError):
    """El pedido de consejo no es válido para el tipo solicitado."""
