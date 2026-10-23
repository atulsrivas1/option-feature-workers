"""Worker-facing error for R26 variants1 runs."""


class VariantWorkerError(Exception):
    """Closed worker error. cause_code/cause_path carry the typed validation cause."""

    def __init__(self, code, cause_code=None, cause_path=None):
        super().__init__(code if cause_code is None else "%s (%s at %s)" % (code, cause_code, cause_path))
        self.code = code
        self.cause_code = cause_code
        self.cause_path = cause_path


def input_invalid(exc):
    """Translate a VariantValidationError into the worker input_invalid class."""
    return VariantWorkerError("input_invalid", cause_code=exc.code, cause_path=exc.path)
