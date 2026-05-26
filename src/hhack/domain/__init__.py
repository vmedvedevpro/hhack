"""Domain models. Import side-effect: registers tables on ``Base.metadata``."""

from hhack.domain.base import Base
from hhack.domain.job import Job
from hhack.domain.match import MatchResult

__all__ = ["Base", "Job", "MatchResult"]
