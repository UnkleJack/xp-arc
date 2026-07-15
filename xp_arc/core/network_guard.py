import ipaddress
import socket
import urllib.parse
import urllib.request


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def public_host(hostname: str, port: int = 443) -> bool:
    if not hostname or hostname.lower() == 'localhost':
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)}
    except (OSError, socket.gaierror):
        return False
    return bool(addresses) and all(_is_public_ip(address) for address in addresses)


def public_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password:
            return False
        if parsed.fragment or not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return public_host(parsed.hostname, port)
    except (TypeError, ValueError, UnicodeError):
        return False


def open_public_url(url: str, timeout: float, context=None):
    if not public_url(url):
        raise ValueError('URL does not resolve exclusively to public addresses')
    opener = urllib.request.build_opener(NoRedirectHandler())
    return opener.open(url, timeout=timeout, context=context)
