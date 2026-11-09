"""Domain errors mapped to HTTP status codes (blueprint §13)."""


class WorkflowError(Exception):
    """An action the rules do not allow in the current state → 409 Conflict."""
    status = 409


class Forbidden(WorkflowError):
    """Actor lacks the role / scope / assignment → 403."""
    status = 403


class Invalid(WorkflowError):
    """Missing or invalid input (reasons, dates, files) → 422."""
    status = 422
