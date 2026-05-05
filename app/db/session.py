import logging
import re
import socket

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# AWS IPv6 prefix → Supabase pooler region (used to pick the right pooler endpoint)
_IPV6_TO_REGION = {
    '2406:da18': 'ap-south-1',
    '2406:da1a': 'ap-southeast-1',
    '2a05:d018': 'eu-west-1',
    '2600:1f18': 'us-east-1',
    '2600:1f1c': 'us-west-1',
    '2406:da14': 'ap-northeast-1',
}

_SUPABASE_DIRECT_HOST = re.compile(r'^db\.([a-z0-9]+)\.supabase\.co$')


def _resolve_db_url(url: str) -> str:
    """Convert a Supabase direct URL (IPv6-only) to the connection-pooler URL (IPv4).

    Render and other providers without IPv6 support cannot reach the Supabase
    direct host.  The pooler endpoint uses IPv4 and works everywhere.
    If the direct host already has an IPv4 record the URL is returned unchanged.
    """
    # Lightweight manual parse to avoid re-encoding issues with urllib.parse
    # Expected format: scheme://user:pass@host:port/dbname
    try:
        scheme_end = url.index('://')
        at_pos = url.rindex('@')          # last '@' — handles encoded '@' (%40) in password
        host_start = at_pos + 1
        path_start = url.index('/', host_start)
        host_port = url[host_start:path_start]
        hostname, port_str = host_port.rsplit(':', 1)
    except ValueError:
        return url

    m = _SUPABASE_DIRECT_HOST.match(hostname)
    if not m or port_str != '5432':
        return url

    ref = m.group(1)

    # If IPv4 is available on the direct host, no conversion needed
    try:
        socket.getaddrinfo(hostname, 5432, socket.AF_INET)
        return url
    except socket.gaierror:
        pass  # IPv6-only — must use pooler

    # Detect region from the IPv6 address prefix
    region = 'ap-south-1'
    try:
        for _, _, _, _, addr in socket.getaddrinfo(hostname, 5432):
            ip = addr[0].lower()
            for prefix, r in _IPV6_TO_REGION.items():
                if ip.startswith(prefix + ':'):
                    region = r
                    break
    except socket.gaierror:
        pass

    pooler_host = f'aws-0-{region}.pooler.supabase.com'

    # Rewrite netloc: change username postgres → postgres.REF and host:port → pooler:6543
    user_info = url[scheme_end + 3:at_pos]                # "user:pass"
    # Supabase direct user is always "postgres"; pooler requires "postgres.REF"
    new_user_info = re.sub(r'^([^:]+):', rf'postgres.{ref}:', user_info, count=1)
    scheme = url[:scheme_end]
    dbname = url[path_start:]
    pooler_url = f'{scheme}://{new_user_info}@{pooler_host}:6543{dbname}'

    logger.warning(
        'Supabase direct URL is IPv6-only; auto-switched to pooler %s:6543', pooler_host
    )
    return pooler_url


settings = get_settings()
_db_url = _resolve_db_url(settings.DATABASE_URL)

if _db_url.startswith('sqlite'):
    _connect_args = {'check_same_thread': False}
    _pool_pre_ping = False
else:
    _connect_args = {'sslmode': 'require'} if 'sslmode' not in _db_url else {}
    _pool_pre_ping = True

engine = create_engine(_db_url, connect_args=_connect_args, pool_pre_ping=_pool_pre_ping)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
