"""Bounded per-task retrieval and source-exact whitespace recovery.

Inspired by task-scoped retrieval and source-span restoration in the reviewed
tax-law project. Independent implementation; neither helper certifies a claim.
"""
from __future__ import annotations
import re


def restore_source_quote(quote, sources):
    """Return original source bytes-as-text, allowing only whitespace layout.

    No fuzzy, case, punctuation, number or negation substitutions are allowed.
    The returned text is always a contiguous substring of one supplied source.
    """
    if not quote or not quote.strip(): return None
    for source in sources:
        if quote in source: return quote
    normalized=' '.join(quote.split())
    for source in sources:
        words=list(re.finditer(r'\S+',source))
        if not words: continue
        folded=' '.join(match.group() for match in words)
        start=folded.find(normalized)
        if start<0: continue
        # Map normalized positions back to exact, untouched source positions.
        positions=[]
        for index,match in enumerate(words):
            if index: positions.append(words[index-1].end())
            positions.extend(range(match.start(),match.end()))
        return source[positions[start]:positions[start+len(normalized)-1]+1]
    return None


def task_bm25_channels(retriever,tasks,existing_queries,max_queries=4):
    """Give independent requests lexical searches without extra LLM calls.

    Results remain candidates and pass the normal temporal/authority/semantic
    gates. Query budgets never remove tasks from answer completeness checks.
    """
    report={'searched_tasks':[], 'deferred_task_ids':[], 'duplicate_task_ids':[]}
    if len(tasks)<2: return [],report
    seen={' '.join(query.split()).casefold() for query in existing_queries}
    channels=[]
    for task in tasks:
        query=' '.join(task.retrieval_query.split())
        key=query.casefold()
        if key in seen:
            report['duplicate_task_ids'].append(task.task_id); continue
        if len(channels)>=max(0,max_queries):
            report['deferred_task_ids'].append(task.task_id); continue
        seen.add(key)
        items=retriever.bm25(query)
        channels.append(items)
        report['searched_tasks'].append({'task_id':task.task_id,'query':query,
          'candidate_ids':[item.unit_id for item in items]})
    return channels,report
