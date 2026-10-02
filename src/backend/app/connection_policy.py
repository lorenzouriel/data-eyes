"""Parse ODBC values without splitting braced passwords; restrict UI destinations."""

import re
from .config import settings


def parse_connection_string(value: str) -> dict[str, str]:
    result = {}
    offset = 0
    while offset < len(value):
        if value[offset] in "; \t\r\n":
            offset += 1
            continue
        match = re.match(r"([^=;{}]+)=", value[offset:])
        if not match:
            raise ValueError("Invalid connection string")
        key = match[1].strip().casefold()
        offset += match.end()
        while offset < len(value) and value[offset].isspace():
            offset += 1
        if offset < len(value) and value[offset] == "{":
            offset += 1
            parts = []
            while offset < len(value):
                char = value[offset]
                offset += 1
                if char == "}":
                    if offset < len(value) and value[offset] == "}":
                        parts.append("}")
                        offset += 1
                        continue
                    break
                parts.append(char)
            else:
                raise ValueError("Unclosed ODBC value")
            item = "".join(parts)
            while offset < len(value) and value[offset].isspace():
                offset += 1
            if offset < len(value) and value[offset] != ";":
                raise ValueError("Invalid ODBC value suffix")
        else:
            end = value.find(";", offset)
            end = len(value) if end < 0 else end
            item = value[offset:end].strip()
            offset = end
        key = {"initial catalog": "database", "user id": "uid", "password": "pwd", "data source": "server"}.get(key, key)
        if key in result:
            raise ValueError("Duplicate connection option")
        result[key] = item
    return result


def validate_connection_string(value: str) -> str:
    if len(value) > 4096:
        raise ValueError("Connection string is too long")
    options = parse_connection_string(value)
    allowed = {"driver", "server", "database", "uid", "pwd", "encrypt", "trustservercertificate", "applicationintent"}
    if set(options) - allowed:
        raise ValueError("Unsupported connection option; use Driver, Server, Database, UID, PWD and TLS options")
    if options.get("driver") != "ODBC Driver 18 for SQL Server":
        raise ValueError("ODBC Driver 18 for SQL Server is required")
    if options.get("server", "").casefold() not in {host.casefold() for host in settings.SQL_ALLOWED_SERVERS}:
        raise ValueError("Server is not in the operator-configured SQL_ALLOWED_SERVERS list")
    if options.get("encrypt", "").casefold() not in {"yes", "mandatory", "strict"}:
        raise ValueError("Encrypt=yes is required")
    if options.get("trustservercertificate", "no").casefold() not in {"no", "false"}:
        raise ValueError("TrustServerCertificate=no is required")
    if not options.get("uid") or not options.get("pwd"):
        raise ValueError("A dedicated SQL login and password are required")
    return value
