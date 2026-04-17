import hashlib
import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_UNIVERSAL_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "corpus" / "universal.yaml"
)


class Probe(BaseModel):
    id: str
    prompt: str
    tags: list[str] = Field(default_factory=list)


class PromptCorpus(BaseModel):
    probes: list[Probe] = Field(default_factory=list)

    def hash(self) -> str:
        """Return a stable sha256 hex digest of the corpus content."""
        payload = "\n".join(
            f"{p.id}\x1f{p.prompt}" for p in sorted(self.probes, key=lambda q: q.id)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_yaml(cls, path: Path) -> "PromptCorpus":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        probes = [Probe.model_validate(item) for item in raw.get("probes", [])]
        return cls(probes=probes)


def load_universal_corpus() -> PromptCorpus:
    """Load the bundled universal probe corpus.

    Returns:
        The universal ``PromptCorpus`` shipped with reagent.
    """
    return PromptCorpus.from_yaml(_UNIVERSAL_CORPUS_PATH)
