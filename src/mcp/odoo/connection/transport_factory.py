from __future__ import annotations

from src.core.credentials import OdooCredentials
from src.mcp.odoo.connection.base_transport import BaseTransportClient
from src.mcp.odoo.connection.json2_transport import Json2TransportClient
from src.mcp.odoo.connection.xmlrpc_transport import XmlRpcTransportClient


def build_transport_client(credentials: OdooCredentials, transport: str) -> BaseTransportClient:
    # Centralize transport construction so the rest of the codebase has exactly
    # one place where string transport names become concrete client instances.
    normalized = transport.strip().lower()
    if normalized == "xmlrpc":
        return XmlRpcTransportClient(credentials)
    if normalized == "json2":
        return Json2TransportClient(credentials)
    raise RuntimeError(f"Unsupported transport {normalized!r}.")