import argparse
import json
import sys
from collections.abc import Callable, Sequence

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database.engine import engine
from app.database.repositories.market import (
    SqlAlchemyMarketCacheRepository,
    market_refresh_lock,
)
from app.database.session import SessionLocal
from app.market.domain import RefreshResult
from app.market.errors import MarketCacheError, MarketRefreshInProgressError
from app.market.esi import EsiClient
from app.market.refresh import MarketCacheRefresher


RESOURCE_CHOICES = (
    "all",
    "orders",
    "adjusted-prices",
    "industry-systems",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh cached public ESI data used by industry costing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh = subparsers.add_parser("refresh", help="Refresh public ESI caches")
    refresh.add_argument(
        "--resource",
        choices=RESOURCE_CHOICES,
        default="all",
        help="Cache resource to refresh (default: all)",
    )
    return parser


def _validate_user_agent(value: str) -> str:
    normalized = value.strip()
    lowered = normalized.casefold()
    if lowered.startswith(("python/", "python-httpx/", "httpx/")):
        raise ValueError("ESI_USER_AGENT must be application-specific")
    if len(normalized) < 8 or "/" not in normalized:
        raise ValueError(
            "ESI_USER_AGENT must identify the application and version"
        )
    return normalized


def _result_json(result: RefreshResult) -> dict[str, str | int]:
    return {
        "resource": result.resource,
        "status": result.status.value,
        "row_count": result.row_count,
        "fresh_until": result.fresh_until.isoformat(),
    }


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, SQLAlchemyError):
        return "Database operation failed"
    return str(exc)


def _refreshers(
    refresher: MarketCacheRefresher,
    resource: str,
) -> Sequence[tuple[str, Callable[[], RefreshResult]]]:
    available = {
        "orders": refresher.refresh_hub_orders,
        "adjusted-prices": refresher.refresh_reference_prices,
        "industry-systems": refresher.refresh_system_cost_indices,
    }
    if resource == "all":
        return tuple(available.items())
    return ((resource, available[resource]),)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    try:
        user_agent = _validate_user_agent(settings.esi_user_agent)
    except ValueError as exc:
        print(f"Market refresh configuration error: {exc}", file=sys.stderr)
        return 1

    results: list[dict[str, str | int]] = []
    errors: list[dict[str, str]] = []
    try:
        with market_refresh_lock(engine) as acquired:
            if not acquired:
                raise MarketRefreshInProgressError(
                    "Another market refresh is already running"
                )
            with SessionLocal() as session, httpx.Client(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=False,
            ) as http_client:
                repository = SqlAlchemyMarketCacheRepository(session)
                esi = EsiClient(
                    http_client,
                    base_url=settings.esi_base_url,
                    compatibility_date=settings.esi_compatibility_date,
                    user_agent=user_agent,
                )
                refresher = MarketCacheRefresher(
                    repository,
                    esi,
                    region_id=settings.market_region_id,
                    location_id=settings.market_location_id,
                )
                for resource, refresh in _refreshers(
                    refresher,
                    args.resource,
                ):
                    try:
                        results.append(_result_json(refresh()))
                    except (MarketCacheError, SQLAlchemyError, ValueError) as exc:
                        errors.append(
                            {
                                "resource": resource,
                                "error": _safe_error_message(exc),
                            }
                        )
    except (MarketCacheError, SQLAlchemyError) as exc:
        errors.append(
            {
                "resource": args.resource,
                "error": _safe_error_message(exc),
            }
        )

    print(
        json.dumps(
            {
                "results": results,
                "errors": errors,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
