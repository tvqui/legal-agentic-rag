from __future__ import annotations
import numpy as np
from .util import stable_id

def _community_description(members:list[dict])->tuple[str,list[str]]:
    """Build a deterministic community description from case evidence."""
    descriptions=[]; keywords=[]
    for case in sorted(members,key=lambda item:item['case_id']):
        heading=' - '.join(str(value).strip() for value in (case.get('case_number'),case.get('dispute'),case.get('court')) if value)
        if heading: descriptions.append(heading[:300])
        for feature in case.get('features') or []:
            value=' '.join(str(feature.get('value') or '').split())
            if value and value not in keywords: keywords.append(value[:120])
    summary='; '.join(descriptions[:8])
    if keywords: summary=(summary+' | Dấu hiệu: '+', '.join(keywords[:20])).strip(' |')
    return summary,keywords[:40]



def build_case_communities(cases: list[dict], embeddings: dict[str,np.ndarray], cfg: dict) -> dict:
    requested=cfg['retrieval'].get('community_algorithm','leiden')
    if requested not in {'leiden','louvain','none'}: raise ValueError('Unsupported community_algorithm')
    if requested=='none': return {'community_nodes':[],'edges':[],'algorithm':'disabled'}
    usable=[c for c in cases if c["case_id"] in embeddings]
    if len(usable) < 3:
        return {"community_nodes":[],"edges":[],"algorithm":"skipped"}
    X=np.vstack([embeddings[c["case_id"]] for c in usable])
    sim=X@X.T
    k=min(int(cfg["retrieval"].get("case_knn_k",3)),len(usable)-1)
    knn=[]
    for i in range(len(usable)):
        idx=np.argsort(-sim[i])
        for j in [x for x in idx if x!=i][:k]:
            a,b=usable[i]["case_id"],usable[j]["case_id"]
            if a < b:
                knn.append((a,b,float(sim[i,j])))
    # Prefer Leiden to mirror LegalGraphRAG; fall back to NetworkX Louvain.
    labels={}
    algo="leiden"
    try:
        if requested=='louvain': raise ImportError('Louvain requested')
        import igraph as ig
        import leidenalg
        ids=[c["case_id"] for c in usable]; pos={x:i for i,x in enumerate(ids)}
        g=ig.Graph(n=len(ids),edges=[(pos[a],pos[b]) for a,b,_ in knn],directed=False)
        weights=[max(w,0.0) for _,_,w in knn]
        part=leidenalg.find_partition(g,leidenalg.RBConfigurationVertexPartition,weights=weights or None)
        for ci,members in enumerate(part):
            for m in members: labels[ids[m]]=ci
    except Exception:
        algo="networkx_louvain"
        import networkx as nx
        g=nx.Graph(); g.add_nodes_from(c["case_id"] for c in usable)
        for a,b,w in knn: g.add_edge(a,b,weight=max(w,0.0))
        parts=nx.community.louvain_communities(g,weight="weight",seed=42)
        for ci,members in enumerate(parts):
            for m in members: labels[m]=ci
    community_nodes=[]; edges=[]
    for ci in sorted(set(labels.values())):
        members=[c for c in usable if labels.get(c["case_id"])==ci]
        cid=stable_id(str(ci),"|".join(sorted(c["case_id"] for c in members)),prefix="community")
        summary,keywords=_community_description(members)
        community_nodes.append({"id":cid,"community_index":ci,"size":len(members),"summary":summary,
          "keywords":keywords,"member_case_ids":sorted(c["case_id"] for c in members)})
        for c in members: edges.append({"source":c["case_id"],"target":cid,"type":"BELONGS_TO","properties":{}})
    for a,b,w in knn: edges.append({"source":a,"target":b,"type":"SIMILAR_TO","properties":{"cosine":w}})
    return {"community_nodes":community_nodes,"edges":edges,"algorithm":algo}
