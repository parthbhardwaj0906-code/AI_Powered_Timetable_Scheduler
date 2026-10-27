from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SolverResult:
    algorithm: str
    success: bool                       # True only for a complete, hard-feasible schedule
    schedule: List[Dict[str, Any]]
    nodes: int = 0                      # assignments tried (backtracking) / iterations (local search)
    elapsed: float = 0.0
    cost_history: List[float] = field(default_factory=list)
    message: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
