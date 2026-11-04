import ipaddress
import re
import socket
from urllib.parse import urlsplit


class URLValidationError(ValueError):
    """Raised when a submitted URL violates security or format requirements."""
    pass


BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "instance-data",
}

DISALLOWED_TLD_SUFFIXES = (
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
)


def is_ip_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address belongs to private, loopback, or reserved ranges."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_and_sanitize_url(url: str, check_dns: bool = True) -> str:
    """
    Validate that a destination URL is strictly HTTP or HTTPS and not an SSRF or scheme vector.
    
    Rules:
    - Must be between 4 and 2048 characters.
    - Scheme strictly 'http' or 'https'.
    - Must include a valid network location (hostname).
    - Must not contain embedded credentials (user:pass@host).
    - Target host must not resolve to loopback, private, link-local, or cloud metadata ranges.
    """
    if not url or not isinstance(url, str):
        raise URLValidationError("URL cannot be empty.")

    url = url.strip()
    if len(url) > 2048:
        raise URLValidationError("URL exceeds maximum permitted length of 2048 characters.")

    try:
        parsed = urlsplit(url)
    except Exception as e:
        raise URLValidationError(f"Invalid URL structure: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise URLValidationError("Only 'http' and 'https' protocols are permitted.")

    if parsed.username or parsed.password:
        raise URLValidationError("URLs containing embedded credentials are not allowed.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise URLValidationError("URL must contain a valid host.")

    if hostname in BLOCKED_HOSTNAMES:
        raise URLValidationError("Access to localhost and internal hostnames is prohibited.")

    if any(hostname.endswith(suffix) for suffix in DISALLOWED_TLD_SUFFIXES):
        raise URLValidationError("Access to local and internal network domains is prohibited.")

    # Check if host is a raw IP literal
    raw_ip = None
    try:
        raw_ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a raw IP literal; proceed to domain name checks
        pass

    if raw_ip is not None:
        if is_ip_disallowed(raw_ip):
            raise URLValidationError(f"Destination IP address '{hostname}' is not permitted.")
        return parsed.geturl()

    # Basic hostname syntax check (RFC 1123)
    if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", hostname) and hostname != "localhost":
        raise URLValidationError(f"Invalid domain name format: {hostname}")

    if check_dns:
        port = parsed.port or (443 if scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            resolved_ips = {item[4][0] for item in addr_info}
            if not resolved_ips:
                raise URLValidationError(f"Unable to resolve host '{hostname}'.")

            for ip_str in resolved_ips:
                ip = ipaddress.ip_address(ip_str)
                if is_ip_disallowed(ip):
                    raise URLValidationError(
                        f"Domain '{hostname}' resolves to restricted internal IP address '{ip_str}'."
                    )
        except socket.gaierror:
            raise URLValidationError(f"Domain '{hostname}' could not be resolved.")
        except Exception as e:
            if isinstance(e, URLValidationError):
                raise
            raise URLValidationError(f"Verification failed for host '{hostname}': {e}")

    return parsed.geturl()
