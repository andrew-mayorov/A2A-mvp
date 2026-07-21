from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class OutboundPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class OutboundPolicy:
    allowed_schemes: frozenset[str]
    allowed_ports: frozenset[int]
    allow_private_networks: bool

    async def validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in self.allowed_schemes:
            raise OutboundPolicyError("Outbound URL scheme is not allowed")
        if parsed.username or parsed.password:
            raise OutboundPolicyError("Credentials in outbound URLs are forbidden")
        if not parsed.hostname:
            raise OutboundPolicyError("Outbound URL hostname is required")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in self.allowed_ports:
            raise OutboundPolicyError("Outbound URL port is not allowed")
        normalized_host = parsed.hostname.rstrip(".").lower()
        if normalized_host in {
            "metadata.google.internal",
            "metadata.azure.internal",
            "instance-data.ec2.internal",
        }:
            raise OutboundPolicyError("Cloud metadata endpoint is forbidden")
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            normalized_host,
            port,
            type=socket.SOCK_STREAM,
        )
        if not addresses:
            raise OutboundPolicyError("Outbound hostname did not resolve")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
                raise OutboundPolicyError("Outbound address range is forbidden")
            if not self.allow_private_networks and (ip.is_private or ip.is_loopback):
                raise OutboundPolicyError("Private or loopback outbound address is forbidden")
