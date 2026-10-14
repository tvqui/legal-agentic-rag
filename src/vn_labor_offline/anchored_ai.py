"""Select source excerpts by ID instead of asking a model to copy legal text.

IDs are local to a fragment. Expansion always uses the original string; no
fuzzy corrections, numeric substitutions or human approvals are made here.
"""
from __future__ import annotations
import copy, json
from .ai_enrichment import cached_structured, structured_cache_key, validate_structured


def quote_field(schema):
    for key, array in schema.get('properties', {}).items():
        if array.get('type') != 'array': continue
        props=array.get('items', {}).get('properties', {})
        for quote in ('source_quote', 'source_text'):
            if quote in props: return key, quote
    return None


def anchors(source, width=200):
    """Partition every character into exact, bounded excerpts, with offsets."""
    rows=[]; start=0
    while start<len(source):
        end=min(start+width,len(source))
        if end<len(source):
            boundary=max(source.rfind('\n',start,end),source.rfind('. ',start,end),source.rfind(';',start,end))
            if boundary>start+width//3: end=boundary+1
        text=source[start:end]
        if text.strip():
            rows.append({'id':f'S{len(rows)+1}','start':start,'end':end,'text':text})
        start=end
    return rows


def anchored_request(requests,system,payload,schema,identity,failed=None):
    field=quote_field(schema)
    if field is None:
        return cached_structured(requests.provider,system,payload,schema,requests.cache,identity,requests.observe),False
    item_key, quote_key=field; excerpts=anchors(payload['source'])
    if not excerpts: raise ValueError('AI_EMPTY_SOURCE')
    bounded=copy.deepcopy(schema)
    array=bounded['properties'][item_key]; array['maxItems']=4
    for key,value in array['items']['properties'].items():
        if value.get('type')=='string' and 'enum' not in value:
            value['maxLength']=200; value['minLength']=1
        if value.get('type')=='array':
            value['maxItems']=6
            if value.get('items',{}).get('type')=='string': value['items']['maxLength']=48
    array['items']['properties'][quote_key]={'type':'string','enum':[row['id'] for row in excerpts]}
    value={**payload,'source_excerpts':excerpts,
           'generation_profile':{'version':'anchored-v1','max_output_tokens':requests.settings.get('ai_max_output_tokens',2048),
               'context_tokens':requests.settings.get('ai_context_tokens',16384)}}
    if failed is not None: value['failed_items_to_reextract']=failed
    prompt=system+f'\nFor {quote_key}, return an excerpt ID from source_excerpts, NEVER copy or rewrite its text. '
    prompt+='Use short values/questions (maximum 200 characters). Return at most 4 atomic items. '
    prompt+='Do not invent missing facts, change numbers, or treat allegations as court findings.'
    if failed is not None:
        prompt+=' Re-extract only the failed items that the source actually supports; do not preserve unsupported claims.'
    data=cached_structured(requests.provider,prompt,value,bounded,requests.cache,identity,requests.observe)
    lookup={row['id']:row['text'] for row in excerpts}
    expanded=copy.deepcopy(data)
    for item in expanded[item_key]: item[quote_key]=lookup[item[quote_key]]
    validate_structured(expanded,schema)
    return expanded,len(data[item_key])>=4


def request_fragment(requests,system,payload,schema,identity):
    # Read valid legacy caches first. Existing successful GPU work is reusable.
    legacy=requests.cache/(structured_cache_key(requests.provider,system,payload,schema,identity)+'.json')
    if legacy.is_file():
        try:
            validate_structured(json.loads(legacy.read_text(encoding='utf-8')),schema)
        except (OSError,ValueError,TypeError): pass
        else:
            data=cached_structured(requests.provider,system,payload,schema,requests.cache,identity,requests.observe)
            field=quote_field(schema)
            saturated=bool(field and len(data[field[0]])>=schema['properties'][field[0]].get('maxItems',100))
            return data,saturated
    if requests.settings.get('ai_compact_output',False):
        return anchored_request(requests,system,payload,schema,identity)
    return cached_structured(requests.provider,system,payload,schema,requests.cache,identity,requests.observe),False


def repair_grounding(requests,system,payload,schema,identity,responses,errors,validator):
    """Preserve valid items and retry only rejected items in batches of four.

    A repair is complete only if enough distinct, validated replacements exist.
    Empty/partial repairs remain explicit failures, rather than a false PASS.
    """
    field=quote_field(schema)
    if field is None: return responses,errors
    item_key,_=field; output=[]; failures=list(errors)
    for response in responses:
        good=[]; bad=[]
        for item in response['data'][item_key]:
            (good if validator(item,response) else bad).append(item)
        unresolved=len(bad)
        if bad and requests.settings.get('ai_grounding_repair',False):
            for batch_index in range(0,len(bad),4):
                batch=bad[batch_index:batch_index+4]
                value={**payload,'source':response['source'],'source_offset':response['source_offset']}
                try:
                    data,_=anchored_request(requests,system,value,schema,
                        identity+':grounding-repair-v1:'+str(batch_index),failed=batch)
                    repaired=[item for item in data[item_key] if validator(item,response)]
                    known={json.dumps(item,sort_keys=True,ensure_ascii=False) for item in good}
                    unique=[]
                    for item in repaired:
                        key=json.dumps(item,sort_keys=True,ensure_ascii=False)
                        if key not in known: unique.append(item); known.add(key)
                    good.extend(unique); unresolved-=min(len(batch),len(unique))
                except Exception as exc:
                    from .ai_requests import error_details
                    failures.append({**error_details(exc),'operation':'grounding_repair',
                        'source_start':response['source_offset'],
                        'source_end':response['source_offset']+len(response['source'])})
        if unresolved:
            failures.append({'reason':'AI_GROUNDING_REPAIR_INCOMPLETE','rejected_items':unresolved,
                'source_start':response['source_offset'],'source_end':response['source_offset']+len(response['source'])})
        output.append({**response,'data':{**response['data'],item_key:good}})
    return output,failures
