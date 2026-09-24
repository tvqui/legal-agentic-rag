def content_match(actual_text: str, expected_identifier: str, expected_title: str = "") -> dict:
    text = (actual_text or "").casefold()
    identifier_ok = bool(expected_identifier and expected_identifier.casefold() in text)
    title_ok = not expected_title or expected_title.casefold() in text
    return {"identifier_match": identifier_ok, "title_match": title_ok, "content_match": identifier_ok and title_ok}
