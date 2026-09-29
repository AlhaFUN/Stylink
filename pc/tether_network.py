"""Find the phone gateway created by Android USB tethering on Windows."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayCandidate:
    interface_alias: str
    description: str
    address: str

    @property
    def is_usb_tether(self) -> bool:
        details = f"{self.interface_alias} {self.description}".casefold()
        return any(word in details for word in ("rndis", "remote ndis", "samsung", "android", "usb"))

    @property
    def label(self) -> str:
        return self.interface_alias or self.description or "Network adapter"


def parse_gateway_output(output: str) -> list[GatewayCandidate]:
    """Parse Get-NetIPConfiguration JSON, tolerating a single-item object."""
    try:
        parsed = json.loads(output.strip()) if output.strip() else []
    except json.JSONDecodeError as error:
        raise ValueError("Windows returned an unreadable network configuration.") from error
    if parsed is None:
        return []
    records = parsed if isinstance(parsed, list) else [parsed]
    found: dict[str, GatewayCandidate] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        alias = str(record.get("interface_alias") or "")
        description = str(record.get("description") or "")
        gateways = record.get("gateways") or []
        if isinstance(gateways, str):
            gateways = [gateways]
        if not isinstance(gateways, list):
            continue
        for raw_address in gateways:
            try:
                address = str(ipaddress.IPv4Address(str(raw_address)))
            except ipaddress.AddressValueError:
                continue
            candidate = GatewayCandidate(alias, description, address)
            previous = found.get(address)
            if previous is None or (candidate.is_usb_tether and not previous.is_usb_tether):
                found[address] = candidate
    return sorted(found.values(), key=lambda candidate: (not candidate.is_usb_tether, candidate.label.casefold(), candidate.address))


def find_gateway_candidates() -> list[GatewayCandidate]:
    """Read IPv4 default gateways without showing a PowerShell window."""
    script = (
        "$ErrorActionPreference='Stop'; "
        "$items = @(Get-NetIPConfiguration | Where-Object { "
        "$_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway } | ForEach-Object { "
        "[pscustomobject]@{ interface_alias=[string]$_.InterfaceAlias; "
        "description=[string]$_.NetAdapter.InterfaceDescription; "
        "gateways=@($_.IPv4DefaultGateway.NextHop) } }); "
        "ConvertTo-Json -InputObject $items -Compress -Depth 3"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return parse_gateway_output(result.stdout)
