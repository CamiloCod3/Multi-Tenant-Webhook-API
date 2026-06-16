import logging, sys
from contextvars import ContextVar

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")

class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get("-")
        return True

def configure_logging(level: str = "INFO"):
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)s [%(name)s] [req=%(correlation_id)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(CorrelationIdFilter())
    root.addHandler(handler)
