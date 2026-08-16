import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.market.domain import (
    CacheMetadata,
    HubPrice,
    MarketPriceLevel,
    ReferencePrice,
    SystemCostIndex,
)
from app.market.errors import (
    EsiOrderPayloadError,
    EsiPayloadError,
    EsiRateLimitError,
    EsiResponseError,
)


_SHARED_MAX_AGE = re.compile(
    r"(?:^|,)\s*s-maxage\s*=\s*\"?(\d+)\"?",
    re.IGNORECASE,
)
_MAX_AGE = re.compile(
    r"(?:^|,)\s*max-age\s*=\s*\"?(\d+)\"?",
    re.IGNORECASE,
)
_ACTIVITY_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CENT = Decimal("0.01")
_MAX_INT64 = 9_223_372_036_854_775_807
_MAX_INT32 = 2_147_483_647


@dataclass(frozen=True, slots=True)
class ConditionalGetResult:
    not_modified: bool
    content: bytes | None
    metadata: CacheMetadata
    page_count: int | None
    rate_limit_remaining: int | None


def _http_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise EsiResponseError("ESI returned an invalid HTTP date") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _compatibility_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EsiResponseError(
            "ESI returned an invalid compatibility date"
        ) from exc


def _non_negative_header(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise EsiResponseError(f"ESI returned an invalid {name} header") from exc
    if parsed < 0:
        raise EsiResponseError(f"ESI returned an invalid {name} header")
    return parsed


def _fresh_until(headers: httpx.Headers, fetched_at: datetime) -> datetime:
    cache_control = headers.get("Cache-Control", "")
    max_age_match = (
        _SHARED_MAX_AGE.search(cache_control)
        or _MAX_AGE.search(cache_control)
    )
    if max_age_match is not None:
        response_date = _http_datetime(headers.get("Date")) or fetched_at
        return response_date + timedelta(seconds=int(max_age_match.group(1)))

    expires = _http_datetime(headers.get("Expires"))
    if expires is None:
        raise EsiResponseError(
            "ESI response has neither Cache-Control max-age nor Expires"
        )
    return expires


class EsiClient:
    """Small conditional-GET client shared by explicit cache refresh jobs."""

    def __init__(
        self,
        http_client: httpx.Client,
        *,
        base_url: str,
        compatibility_date: date,
        user_agent: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("ESI user agent must not be blank")
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._compatibility_date = compatibility_date
        self._user_agent = user_agent.strip()
        self._now = now or (lambda: datetime.now(UTC))

    def now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("ESI client clock must return an aware datetime")
        return current.astimezone(UTC)

    @property
    def compatibility_date(self) -> date:
        return self._compatibility_date

    def conditional_get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        cached: CacheMetadata | None = None,
    ) -> ConditionalGetResult:
        headers = {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "X-Compatibility-Date": self._compatibility_date.isoformat(),
        }
        revalidation_cache = (
            cached
            if cached is not None
            and cached.requested_compatibility_date
            == self._compatibility_date
            else None
        )
        if revalidation_cache is not None and revalidation_cache.etag is not None:
            headers["If-None-Match"] = revalidation_cache.etag

        try:
            response = self._http.get(
                f"{self._base_url}/{path.lstrip('/')}",
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise EsiResponseError("ESI request failed") from exc

        retry_after = _non_negative_header(response.headers, "Retry-After")
        if response.status_code == 429:
            raise EsiRateLimitError(retry_after)
        if response.status_code == 420:
            raise EsiRateLimitError(
                _non_negative_header(
                    response.headers,
                    "X-ESI-Error-Limit-Reset",
                )
            )
        if response.status_code not in (200, 304):
            raise EsiResponseError(f"ESI returned HTTP {response.status_code}")
        if response.status_code == 304 and revalidation_cache is None:
            raise EsiResponseError("ESI returned 304 without a cached response")

        fetched_at = self.now()
        metadata = CacheMetadata(
            etag=(
                response.headers.get("ETag")
                or (revalidation_cache.etag if revalidation_cache is not None else None)
            ),
            last_modified_at=(
                _http_datetime(response.headers.get("Last-Modified"))
                or (
                    revalidation_cache.last_modified_at
                    if revalidation_cache is not None
                    else None
                )
            ),
            fresh_until=_fresh_until(response.headers, fetched_at),
            fetched_at=fetched_at,
            requested_compatibility_date=self._compatibility_date,
            matched_compatibility_date=(
                _compatibility_date(response.headers.get("X-Compatibility-Date"))
                or (
                    revalidation_cache.matched_compatibility_date
                    if revalidation_cache is not None
                    else None
                )
            ),
        )
        page_count = _non_negative_header(response.headers, "X-Pages")
        if page_count == 0:
            raise EsiResponseError("ESI returned an invalid X-Pages header")

        legacy_errors_remaining = _non_negative_header(
            response.headers,
            "X-ESI-Error-Limit-Remain",
        )
        if legacy_errors_remaining == 0:
            raise EsiRateLimitError(
                _non_negative_header(
                    response.headers,
                    "X-ESI-Error-Limit-Reset",
                )
            )

        return ConditionalGetResult(
            not_modified=response.status_code == 304,
            content=None if response.status_code == 304 else response.content,
            metadata=metadata,
            page_count=page_count,
            rate_limit_remaining=_non_negative_header(
                response.headers,
                "X-Ratelimit-Remaining",
            ),
        )


def _reject_json_constant(value: str) -> None:
    raise EsiPayloadError(f"ESI JSON contains invalid number {value}")


def _json_list(content: bytes) -> list[Any]:
    try:
        payload = json.loads(
            content,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EsiPayloadError("ESI returned invalid JSON") from exc
    if not isinstance(payload, list):
        raise EsiPayloadError("ESI response must be a JSON array")
    return payload


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EsiPayloadError(f"{field} must be an object")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    maximum: int = _MAX_INT64,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EsiPayloadError(f"{field} must be an integer")
    if not 0 < value <= maximum:
        raise EsiPayloadError(f"{field} is outside the supported range")
    return value


def _decimal(
    value: Any,
    field: str,
    *,
    money: bool = False,
    allow_zero: bool = False,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise EsiPayloadError(f"{field} must be a number")
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed < 0 or (parsed == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise EsiPayloadError(f"{field} must be {qualifier} and finite")
    if money and parsed != parsed.quantize(_CENT):
        raise EsiPayloadError(f"{field} has precision below 0.01 ISK")
    return parsed


def _order_payload_error(
    *,
    page: int,
    row_number: int,
    row: Mapping[str, Any] | None,
    field: str,
    rejected_value: Any,
    reason: str,
) -> EsiOrderPayloadError:
    order_id = row.get("order_id") if row is not None else None
    return EsiOrderPayloadError(
        page=page,
        row=row_number,
        order_id=order_id,
        field=field,
        rejected_value=rejected_value,
        reason=reason,
    )


def _order_integer(
    row: Mapping[str, Any],
    field: str,
    *,
    page: int,
    row_number: int,
    maximum: int = _MAX_INT64,
) -> int:
    value = row.get(field)
    try:
        return _integer(value, field, maximum=maximum)
    except EsiPayloadError as exc:
        raise _order_payload_error(
            page=page,
            row_number=row_number,
            row=row,
            field=field,
            rejected_value=value,
            reason=str(exc),
        ) from exc


def _order_decimal(
    row: Mapping[str, Any],
    field: str,
    *,
    page: int,
    row_number: int,
) -> Decimal:
    value = row.get(field)
    try:
        return _decimal(value, field, money=True)
    except EsiPayloadError as exc:
        raise _order_payload_error(
            page=page,
            row_number=row_number,
            row=row,
            field=field,
            rejected_value=value,
            reason=str(exc),
        ) from exc


def _checked_level_volume(
    current: int,
    added: int,
    *,
    page: int,
    row_number: int,
    row: Mapping[str, Any],
) -> int:
    total = current + added
    if total > _MAX_INT64:
        raise _order_payload_error(
            page=page,
            row_number=row_number,
            row=row,
            field="volume_remain",
            rejected_value=row.get("volume_remain"),
            reason="Aggregated market volume exceeds BIGINT",
        )
    return total


def parse_hub_order_page(
    content: bytes,
    *,
    location_id: int,
    page: int = 1,
) -> tuple[HubPrice, ...]:
    """Parse one ESI order page into station-scoped aggregated price depth."""
    if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
        raise ValueError("page must be a positive integer")

    quotes: dict[int, dict[str, dict[Decimal, int]]] = {}
    for index, raw_row in enumerate(_json_list(content)):
        row_number = index + 1
        if not isinstance(raw_row, dict):
            raise _order_payload_error(
                page=page,
                row_number=row_number,
                row=None,
                field="row",
                rejected_value=raw_row,
                reason=f"orders[{index}] must be an object",
            )
        row = raw_row
        row_location_id = _order_integer(
            row,
            "location_id",
            page=page,
            row_number=row_number,
        )
        if row_location_id != location_id:
            continue

        raw_volume = row.get("volume_remain")
        # ESI may briefly expose an exhausted order while a cached page is being
        # refreshed. Exact integer zero is a legitimate exhausted order and is
        # ignored. Numeric-looking strings/floats and negative values remain
        # malformed instead of being silently coerced.
        if type(raw_volume) is int and raw_volume == 0:
            continue
        volume = _order_integer(
            row,
            "volume_remain",
            page=page,
            row_number=row_number,
        )
        type_id = _order_integer(
            row,
            "type_id",
            page=page,
            row_number=row_number,
            maximum=_MAX_INT32,
        )
        is_buy_order = row.get("is_buy_order")
        if not isinstance(is_buy_order, bool):
            raise _order_payload_error(
                page=page,
                row_number=row_number,
                row=row,
                field="is_buy_order",
                rejected_value=is_buy_order,
                reason="is_buy_order must be a boolean",
            )
        price = _order_decimal(
            row,
            "price",
            page=page,
            row_number=row_number,
        )
        if is_buy_order:
            raw_min_volume = row.get("min_volume", 1)
            try:
                min_volume = _integer(raw_min_volume, "min_volume")
            except EsiPayloadError as exc:
                raise _order_payload_error(
                    page=page,
                    row_number=row_number,
                    row=row,
                    field="min_volume",
                    rejected_value=raw_min_volume,
                    reason=str(exc),
                ) from exc
            if min_volume > 1:
                continue

        quote = quotes.setdefault(type_id, {"buy": {}, "sell": {}})
        side = "buy" if is_buy_order else "sell"
        levels = quote[side]
        levels[price] = _checked_level_volume(
            levels.get(price, 0),
            volume,
            page=page,
            row_number=row_number,
            row=row,
        )

    result: list[HubPrice] = []
    for type_id, quote in sorted(quotes.items()):
        buy_levels = tuple(
            MarketPriceLevel(price=price, volume=volume)
            for price, volume in sorted(
                quote["buy"].items(),
                key=lambda item: item[0],
                reverse=True,
            )
        )
        sell_levels = tuple(
            MarketPriceLevel(price=price, volume=volume)
            for price, volume in sorted(quote["sell"].items(), key=lambda item: item[0])
        )
        result.append(
            HubPrice(
                type_id=type_id,
                best_buy_price=buy_levels[0].price if buy_levels else None,
                best_buy_volume=buy_levels[0].volume if buy_levels else None,
                best_sell_price=sell_levels[0].price if sell_levels else None,
                best_sell_volume=sell_levels[0].volume if sell_levels else None,
                buy_levels=buy_levels,
                sell_levels=sell_levels,
            )
        )
    return tuple(result)


def parse_reference_prices(content: bytes) -> tuple[ReferencePrice, ...]:
    prices: list[ReferencePrice] = []
    seen_type_ids: set[int] = set()
    for index, raw_row in enumerate(_json_list(content)):
        row = _object(raw_row, f"prices[{index}]")
        type_id = _integer(row.get("type_id"), "type_id", maximum=_MAX_INT32)
        if type_id in seen_type_ids:
            raise EsiPayloadError(f"duplicate reference price for type {type_id}")
        seen_type_ids.add(type_id)
        adjusted = row.get("adjusted_price")
        average = row.get("average_price")
        prices.append(
            ReferencePrice(
                type_id=type_id,
                adjusted_price=(
                    _decimal(adjusted, "adjusted_price", allow_zero=True)
                    if adjusted is not None
                    else None
                ),
                average_price=(
                    _decimal(average, "average_price", allow_zero=True)
                    if average is not None
                    else None
                ),
            )
        )
    return tuple(sorted(prices, key=lambda price: price.type_id))


def parse_system_cost_indices(content: bytes) -> tuple[SystemCostIndex, ...]:
    indices: list[SystemCostIndex] = []
    seen: set[tuple[int, str]] = set()
    for system_index, raw_system in enumerate(_json_list(content)):
        system = _object(raw_system, f"systems[{system_index}]")
        solar_system_id = _integer(
            system.get("solar_system_id"),
            "solar_system_id",
            maximum=_MAX_INT32,
        )
        raw_indices = system.get("cost_indices")
        if not isinstance(raw_indices, list):
            raise EsiPayloadError("cost_indices must be an array")
        for cost_index, raw_index in enumerate(raw_indices):
            entry = _object(
                raw_index,
                f"systems[{system_index}].cost_indices[{cost_index}]",
            )
            activity = entry.get("activity")
            if not isinstance(activity, str) or not _ACTIVITY_CODE.fullmatch(activity):
                raise EsiPayloadError("activity has an invalid value")
            raw_cost_index = entry.get("cost_index")
            if isinstance(raw_cost_index, bool) or not isinstance(
                raw_cost_index,
                (int, Decimal),
            ):
                raise EsiPayloadError("cost_index must be a number")
            parsed_cost_index = Decimal(raw_cost_index)
            if not parsed_cost_index.is_finite() or parsed_cost_index < 0:
                raise EsiPayloadError("cost_index must be non-negative and finite")
            key = (solar_system_id, activity)
            if key in seen:
                raise EsiPayloadError(
                    f"duplicate system cost index for {solar_system_id}/{activity}"
                )
            seen.add(key)
            indices.append(
                SystemCostIndex(
                    solar_system_id=solar_system_id,
                    activity=activity,
                    cost_index=parsed_cost_index,
                )
            )
    return tuple(
        sorted(indices, key=lambda item: (item.solar_system_id, item.activity))
    )
