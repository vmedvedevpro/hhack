"""Domain models. Import side-effect: registers tables on ``Base.metadata``."""

from hhack.domain.base import Base
from hhack.domain.job import Job

__all__ = ["Base", "Job"]
