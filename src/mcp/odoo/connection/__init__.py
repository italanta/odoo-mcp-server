"""Odoo connection layer: client facade plus transport backends.

This package exists to make the transport boundary explicit.
Code outside this package should normally depend on ``OdooClient`` only,
while transport selection and per-transport request details stay isolated here.
"""

# Re-export the facade so callers can import a stable top-level client symbol
# without needing to know which transport backend it will choose internally.
from src.mcp.odoo.connection.client import OdooClient

__all__ = ["OdooClient"]