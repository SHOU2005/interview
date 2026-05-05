import logging
import os
import re
import socket

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SUPABASE_DIRECT_HOST = re.compile(r'^db\.([a-z0-9]+)\.supabase\.co$')

_POOLER_REGIONS = [
    'ap-southeast-1',
    'ap-south-1',
    'us-east-1',
    'eu-west-1',
    'us-west-1',
    'ap-northeast-1',
    'eu-central-1',
    'sa-east-1',
]


def _find_pooler_region(ref: str) -> str:
    """Find the Supabase pooler region that hosts this project.

    Probes each regional pooler with a dummy password:
      - "Tenant or user not found"  → wrong region, try next
      - any other error (auth fail) → correct region
    Set SUPABASE_REGION env var to skip probing entirely.
    """
    override = os.environ.get('SUPABASE_REGION', '').strip()
    if override:
        logger.info('Using SUPABASE_REGION override: %s', override)
        return override

    import psycopg2

    for region in _POOLER_REGIONS:
        host = f'aws-0-{region}.pooler.supabase.com'
        try:
            conn = psycopg2.connect(
                host=host,
                port=6543,
                user=f'postgres.{ref}',
                password='__probe__',
                dbname='postgres',
                connect_timeout=5,
                sslmode='require',
            )
            conn.close()
            logger.info('Supabase pooler region: %s', region)
            return region
        except psycopg2.OperationalError as exc:
            msg = str(exc).lower()
            if 'tenant' in msg or 'not found' in msg:
                continue  # wrong region
            # Auth failure or anything else means this region hosts the project
            logger.info('Supabase pooler region: %s', region)
            return region
        except Exception:
            continue

    logger.warning('Could not detect Supabase pooler region; falling back to ap-southeast-1')
    return 'ap-southeast-1'


def _resolve_db_url(url: str) -> str:
    """Convert a Supabase direct URL (IPv6-only) to the IPv4 connection-pooler URL."""
    try:
        scheme_end = url.index('://')
        at_pos = url.rindex('@')      # last '@' so encoded '%40' in password is safe
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

    # Direct host has IPv4 → no conversion needed
    try:
        socket.getaddrinfo(hostname, 5432, socket.AF_INET)
        return url
    except socket.gaierror:
        pass  # IPv6-only, must use pooler

    region = _find_pooler_region(ref)
    pooler_host = f'aws-0-{region}.pooler.supabase.com'

    user_info = url[scheme_end + 3:at_pos]
    new_user_info = re.sub(r'^([^:]+):', rf'postgres.{ref}:', user_info, count=1)
    scheme = url[:scheme_end]
    dbname = url[path_start:]
    pooler_url = f'{scheme}://{new_user_info}@{pooler_host}:6543{dbname}'

    logger.warning('Supabase direct URL is IPv6-only; switched to pooler %s:6543', pooler_host)
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
