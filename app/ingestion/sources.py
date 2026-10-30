from typing import Protocol


class ArtifactSource(Protocol):
    async def read(self) -> bytes:
        """Return the complete artifact content."""
        ...