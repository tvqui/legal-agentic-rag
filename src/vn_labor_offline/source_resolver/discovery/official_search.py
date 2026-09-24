def build_query(identifier: str, title: str = "") -> str:
    return " ".join(part for part in (identifier, title) if part).strip()
