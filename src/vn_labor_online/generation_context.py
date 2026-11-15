"""Context-safe generation views. Whole sources and the original plan survive."""
from copy import deepcopy
import json
from .context_budget import fits_context
from .errors import StructuredOutputError

def encode_payload(payload):
    return json.dumps(payload,ensure_ascii=False,separators=(',',':'))

def generation_batches(provider,system,payload,max_batches=8):
    # Remove only unknown transport metadata; preserve text byte-for-byte.
    compact=deepcopy(payload)
    compact['evidence']=[{k:v for k,v in item.items() if v is not None} for item in payload.get('evidence',[])]
    if fits_context(provider,system,encode_payload(compact)):return [compact]
    sources=compact['evidence'];base={k:v for k,v in compact.items() if k!='evidence'}
    base['batch_instruction']='Draft only propositions supported by this batch of complete sources. The full plan is global; do not invent unseen sources or claim full coverage. Other source batches are combined and independently reviewed.'
    batches=[];current=[]
    for source in sources:
        candidate={**base,'evidence':current+[source]}
        if fits_context(provider,system,encode_payload(candidate)):
            current.append(source);continue
        if current:batches.append({**base,'evidence':current});current=[]
        single={**base,'evidence':[source]}
        if not fits_context(provider,system,encode_payload(single)):
            raise StructuredOutputError('GENERATION_SOURCE_CONTEXT_OVERFLOW')
        current=[source]
    if current:batches.append({**base,'evidence':current})
    if not batches or len(batches)>max_batches:
        raise StructuredOutputError('GENERATION_CONTEXT_BATCH_LIMIT')
    return batches
