from typing import Tuple

try:
    # SQLAlchemy 1.4+
    from sqlalchemy.orm import DeclarativeMeta
except ImportError:
    from sqlalchemy.ext.declarative.api import DeclarativeMeta  # type: ignore

Model = DeclarativeMeta
ResponseTuple = Tuple[dict, int, dict]
