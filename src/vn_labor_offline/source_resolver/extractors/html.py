from bs4 import BeautifulSoup


def extract_text(payload: bytes) -> str:
    return BeautifulSoup(payload, "html.parser").get_text(" ", strip=True)
