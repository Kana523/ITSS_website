class SdeError(Exception):
    """Base error for SDE source, validation, and import failures."""


class SdeSourceError(SdeError):
    """Raised when required SDE source files cannot be opened."""


class SdeValidationError(SdeError):
    """Raised when SDE input violates the supported data contract."""


class SdeImportConflictError(SdeError):
    """Raised when a build number was already imported from different data."""
