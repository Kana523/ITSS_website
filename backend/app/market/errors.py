class MarketCacheError(Exception):
    """Base error for public ESI cache refreshes."""


class EsiResponseError(MarketCacheError):
    """ESI returned an unusable HTTP response."""


class EsiPayloadError(MarketCacheError, ValueError):
    """ESI returned data that violates the expected contract."""


class EsiRateLimitError(MarketCacheError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        message = "ESI rate limit does not permit completing this refresh"
        if retry_after_seconds is not None:
            message += f"; retry after {retry_after_seconds} seconds"
        super().__init__(message)


class MarketRefreshInProgressError(MarketCacheError):
    """Another process currently owns the market refresh lock."""
