from typing import Any


class MarketCacheError(Exception):
    """Base error for public ESI cache refreshes."""


class EsiResponseError(MarketCacheError):
    """ESI returned an unusable HTTP response."""


class EsiPayloadError(MarketCacheError, ValueError):
    """ESI returned data that violates the expected contract."""


class EsiOrderPayloadError(EsiPayloadError):
    """Malformed market-order data with enough context to diagnose the row."""

    def __init__(
        self,
        *,
        page: int,
        row: int,
        order_id: int | str | None,
        field: str,
        rejected_value: Any,
        reason: str,
    ) -> None:
        self.page = page
        self.row = row
        self.order_id = order_id
        self.field = field
        self.rejected_value = rejected_value
        self.reason = reason
        display_order_id = "<missing>" if order_id is None else repr(order_id)
        super().__init__(
            "Malformed ESI market order: "
            f"page={page}, row={row}, order_id={display_order_id}, "
            f"field={field}, rejected_value={rejected_value!r}: {reason}"
        )


class EsiRateLimitError(MarketCacheError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        message = "ESI rate limit does not permit completing this refresh"
        if retry_after_seconds is not None:
            message += f"; retry after {retry_after_seconds} seconds"
        super().__init__(message)


class MarketRefreshInProgressError(MarketCacheError):
    """Another process currently owns the market refresh lock."""
