"""Exact source-span selection: models select IDs, never rewrite quotations."""
import re

def source_spans(text):
    if not isinstance(text,str) or not text.strip():return {}
    spans=[];start=0
    boundaries=[m.end() for m in re.finditer(r';|\n',text)]+[len(text)]
    for end in boundaries:
        if end<=start:continue
        if len(text[start:end].strip())<8:continue
        spans.append((start,end));start=end
    if start<len(text):
        if spans:spans[-1]=(spans[-1][0],len(text))
        else:spans=[(0,len(text))]
    # Preserve all bytes and their order, grouping adjacent spans for large
    # sources. This is a display/selection index, not statutory segmentation.
    while len(spans)>24:
        spans=[(spans[i][0],spans[min(i+1,len(spans)-1)][1]) for i in range(0,len(spans),2)]
    return {f'span_{i:03d}':text[a:b].strip() for i,(a,b) in enumerate(spans) if text[a:b].strip()}
