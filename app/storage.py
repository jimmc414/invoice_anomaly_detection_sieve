"""Shared storage clients (database, cache, object storage, search)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

try:  # Optional imports for environments where optional deps are missing
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore

try:
    from opensearchpy import OpenSearch
except ImportError:  # pragma: no cover
    OpenSearch = None  # type: ignore

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore


engine = create_engine(settings.db_dsn, pool_pre_ping=True, future=True)
# SQLAlchemy engine used across the application.

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
# Session factory bound to the configured database DSN.


if boto3:
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_key,
        aws_secret_access_key=settings.s3_secret,
    )
else:  # pragma: no cover - boto3 unavailable in minimal CI
    s3 = None


if OpenSearch:
    os_client = OpenSearch(hosts=[settings.os_host])
else:  # pragma: no cover - OpenSearch optional for unit tests
    os_client = None


if redis:
    redis_client = redis.Redis.from_url(settings.redis_url)
else:  # pragma: no cover
    redis_client = None


@contextmanager
def session_scope() -> Iterator:
    """Provide a transactional scope around a series of operations."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_redis_client():
    """Return the configured Redis client, raising if not available."""

    if redis_client is None:  # pragma: no cover - primarily for runtime
        raise RuntimeError("Redis client is not configured")
    return redis_client
