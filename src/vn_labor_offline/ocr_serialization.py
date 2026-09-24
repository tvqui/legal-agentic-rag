"""Preserve legal list markers and text nested inside scanned-picture regions."""


def legal_plain_text(document):
    from docling_core.transforms.serializer.plain_text import PlainTextDocSerializer, PlainTextParams
    from docling_core.transforms.serializer.markdown import OrigListItemMarkerMode
    # The default serializer adds valid Markdown list numbering. Legal numbers
    # are source data: do not manufacture them to make a Markdown list valid.
    return PlainTextDocSerializer(doc=document, params=PlainTextParams(
        traverse_pictures=True,
        ensure_valid_list_item_marker=False,
        orig_list_item_marker_mode=OrigListItemMarkerMode.ALWAYS,
    )).serialize().text


def reading_lines(cells):
    """Order OCR cells geometrically without adding numbering or losing words.

    Input boxes are top-left coordinates. This is row reading order, suitable
    for the corpus's single-column legal pages; retain boxes for manual review.
    """
    rows=[]
    for cell in sorted(cells, key=lambda c: ((c['top']+c['bottom'])/2, c['left'])):
        height=max(1, cell['bottom']-cell['top'])
        middle=(cell['top']+cell['bottom'])/2
        if rows and abs(middle-rows[-1]['middle']) <= .4*min(height, rows[-1]['height']):
            rows[-1]['cells'].append(cell)
        else:
            rows.append({'middle':middle, 'height':height, 'cells':[cell]})
    return '\n'.join(' '.join(c['text'].strip() for c in sorted(row['cells'],key=lambda c:c['left'])
                              if c['text'].strip()) for row in rows)


def conversion_text(result):
    pages=[]
    for page in result.pages:
        cells=[]
        for cell in page.cells:
            box=cell.rect.to_bounding_box().to_top_left_origin(page.size.height)
            cells.append({'text':cell.text,'left':box.l,'top':box.t,'right':box.r,'bottom':box.b,
                          'confidence':cell.confidence,'from_ocr':cell.from_ocr})
        pages.append({'page':page.page_no,'cells':cells})
    text='\n\n'.join(reading_lines(page['cells']) for page in pages).strip()
    return (text or legal_plain_text(result.document)), pages
