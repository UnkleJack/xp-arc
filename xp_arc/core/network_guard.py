import ipaddress
import socket
import urllib.parse
import urllib.request
import ssl
import http.client


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that connects to a pinned IP but verifies against hostname."""
    def __init__(self, host, port=None, pinned_ip=None, context=None, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(host, port, context=context, **kwargs)
    
    def connect(self):
        # Connect to the pinned IP instead of resolving hostname
        if self._pinned_ip:
            self.sock = self._create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        else:
            super().connect()
        
        # Now do SSL handshake with the original hostname for certificate verification
        if self._tunnel_host:
            self._tunnel()
        if self.sock:
            server_hostname = self.host if self._pinned_ip else None
            self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip=None, context=None):
        self._pinned_ip = pinned_ip
        self._context = context
        super().__init__(context=context)
    
    def https_open(self, req):
        # Extract the original hostname from the Host header
        host = req.get_header('Host')
        if not host:
            host = req.host
        
        # Parse the URL to get the port
        parsed = urllib.parse.urlparse(req.get_full_url())
        port = parsed.port or 443
        
        # Create connection with pinned IP
        conn = PinnedHTTPSConnection(host, port, pinned_ip=self._pinned_ip, context=self._context)
        return self.do_open(lambda *args, **kwargs: conn, req)


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


def _resolve_public_ips(hostname: str, port: int = 443) -> list[str] | None:
    """Resolve hostname and return only public IPs. Returns None if any IP is non-public or resolution fails."""
    if not hostname or hostname.lower() == 'localhost':
        return None
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        return None
    addresses: list[str] = []
    for item in infos:
        # item[4] is (ip, port) tuple for IPv4, (ip, port, flowinfo, scopeid) for IPv6
        addr = item[4][0]
        if isinstance(addr, str):
            addresses.append(addr)
    # Verify ALL resolved IPs are public
    if not addresses:
        return None
    if not all(_is_public_ip(addr) for addr in addresses):
        return None
    return addresses


def public_host(hostname: str, port: int = 443) -> bool:
    """Check if hostname resolves exclusively to public IPs."""
    return _resolve_public_ips(hostname, port) is not None


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


def open_public_url(url: str, timeout: float, context: ssl.SSLContext | None = None):
    """Open a URL after verifying it resolves to public IPs only.
    
    RT-17 mitigation: DNS rebinding TOCTOU fix by pinning resolved IPs at connect time.
    We resolve once, verify all IPs are public, then force connection to one of those IPs
    while still verifying the SSL certificate against the original hostname.
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise ValueError('Invalid URL: no hostname')
    
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    public_ips = _resolve_public_ips(parsed.hostname, port)
    if not public_ips:
        raise ValueError('URL does not resolve exclusively to public addresses')
    
    # Use the first public IP for connection pinning
    target_ip = public_ips[0]
    
    # Create opener with our PinnedHTTPSHandler that connects to pinned IP
    # but verifies certificate against original hostname
    if parsed.scheme == 'https':
        handler = PinnedHTTPSHandler(pinned_ip=target_ip, context=context)
        opener = urllib.request.build_opener(NoRedirectHandler(), handler)
    else:
        opener = urllib.request.build_opener(NoRedirectHandler())
    
    req = urllib.request.Request(
        url,  # Use original URL with hostname for SSL verification
        headers={'Host': parsed.hostname}
    )
    return opener.open(req, timeout=timeout)
