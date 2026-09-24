class SearxngDiscovery:
    """Optional protocol boundary; network access is deliberately opt-in."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    def search(self, query: str) -> list[dict]:
        raise NotImplementedError("SearXNG discovery is opt-in and needs an explicit transport")
