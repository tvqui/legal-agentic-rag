"""Isolated official LightRAG/HippoRAG2 retrieval worker; JSONL over stdio.

No Gold is accepted by this process. Build cost is measured separately. Native
QA is intentionally not called: the parent uses the same reader for every
retriever, with exactly the same context budget and evaluator.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class Native:
    def __init__(self, cfg):
        self.cfg = cfg
        if digest(cfg['corpus']) != cfg['corpus_sha256']:
            raise ValueError('Corpus fingerprint mismatch')
        self.units = [json.loads(s) for s in Path(cfg['corpus']).read_text(encoding='utf-8').splitlines()]
        self.texts = [u['display_text'] for u in self.units]
        self.ids = [u['unit_id'] for u in self.units]
        # Distinct source records can have identical text. Never guess an ID
        # from a duplicate passage; give the worker an unambiguous source tag.
        self.tagged = [f'[SOURCE_ID={uid}]\n{text}' for uid, text in zip(self.ids, self.texts)]
        self.tagged_by_id = dict(zip(self.ids, self.tagged))
        self.reverse = dict(zip(self.tagged, self.ids))
        self.work = Path(cfg['work_dir']); self.work.mkdir(parents=True, exist_ok=True)
        identity = {k: cfg.get(k) for k in ('method', 'commit', 'corpus_sha256', 'llm_model', 'llm_base_url',
                   'embedding_model', 'embedding_base_url', 'embedding_model_identity', 'embedding_dim', 'chunk_token_size')}
        manifest = self.work / 'index_identity.json'
        if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')) != identity:
            raise ValueError('Existing index belongs to different corpus/models/config')
        if not manifest.exists() and any(self.work.iterdir()):
            raise ValueError('Refuse untracked pre-existing external index')
        manifest.write_text(json.dumps(identity, indent=2), encoding='utf-8')
        self.calls = 0

    async def build_light(self):
        from lightrag import LightRAG, QueryParam
        from lightrag.utils import EmbeddingFunc
        from openai import AsyncOpenAI
        import numpy as np
        cfg = self.cfg
        self.chat = AsyncOpenAI(base_url=cfg['llm_base_url'], api_key=os.environ.get(cfg.get('llm_api_key_env', 'BASELINE_API_KEY'), 'ollama'), max_retries=0)
        self.embed = AsyncOpenAI(base_url=cfg['embedding_base_url'], api_key=os.environ.get(cfg.get('embedding_api_key_env', 'BASELINE_API_KEY'), 'ollama'), max_retries=0)

        async def llm(prompt, system_prompt=None, history_messages=None, **kwargs):
            messages = []
            if system_prompt: messages.append({'role': 'system', 'content': system_prompt})
            messages += history_messages or []
            messages.append({'role': 'user', 'content': prompt})
            self.calls += 1
            response = await self.chat.chat.completions.create(model=cfg['llm_model'], messages=messages,
                temperature=0, max_tokens=cfg.get('extraction_output_tokens', 4096))
            return response.choices[0].message.content

        async def embeddings(texts):
            response = await self.embed.embeddings.create(model=cfg['embedding_model'], input=texts)
            return np.asarray([e.embedding for e in sorted(response.data, key=lambda e: e.index)])

        self.query_param = QueryParam
        self.engine = LightRAG(working_dir=str(self.work / 'index'), llm_model_func=llm,
            llm_model_name=cfg['llm_model'], embedding_func=EmbeddingFunc(embedding_dim=cfg['embedding_dim'],
            max_token_size=cfg.get('embedding_max_tokens', 8192), func=embeddings),
            chunk_token_size=cfg.get('chunk_token_size', 1200), chunk_overlap_token_size=0)
        await self.engine.initialize_storages()
        # Upstream insertion is idempotent and checkpoints individual documents.
        # ALL corpus units are passed, never a Gold-positive subset.
        await self.engine.ainsert(self.tagged, ids=self.ids, file_paths=self.ids)

    def build_hippo(self):
        from hipporag import HippoRAG
        cfg = self.cfg
        self.local_dummy_key(cfg['llm_base_url'], cfg.get('llm_api_key_env', 'BASELINE_API_KEY'))
        self.local_dummy_key(cfg['embedding_base_url'], cfg.get('embedding_api_key_env', 'BASELINE_API_KEY'))
        self.engine = HippoRAG(save_dir=str(self.work / 'index'), llm_model_name=cfg['llm_model'],
            llm_base_url=cfg['llm_base_url'], embedding_model_name=cfg['embedding_model'],
            embedding_base_url=cfg['embedding_base_url'], embedding_provider='openai', llm_api_key_env=cfg.get('llm_api_key_env', 'BASELINE_API_KEY'),
            embedding_api_key_env=cfg.get('embedding_api_key_env', 'BASELINE_API_KEY'))
        self.engine.index(self.tagged)

    @staticmethod
    def local_dummy_key(url, name):
        from urllib.parse import urlsplit
        if urlsplit(url).hostname in {'127.0.0.1', 'localhost', '::1'}:
            os.environ.setdefault(name, 'local-service-not-a-secret')
        elif not os.environ.get(name):
            raise ValueError('Missing baseline provider credential environment variable')

    def prepare(self):
        import importlib.metadata
        start = time.perf_counter()
        if self.cfg['method'] == 'lightrag':
            self.loop = asyncio.new_event_loop()
            self.loop.run_until_complete(self.build_light())
        elif self.cfg['method'] == 'hipporag2':
            self.build_hippo()
        else:
            raise ValueError('No verified native retrieval API adapter')
        packages = {}
        for name in ('lightrag-hku', 'hipporag', 'openai', 'numpy', 'torch', 'transformers'):
            try: packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: pass
        return {'status': 'OK', 'units_indexed': len(self.ids), 'index_build_ms': (time.perf_counter() - start) * 1000,
                'index_llm_calls': self.calls if self.cfg['method'] == 'lightrag' else None,
                'worker_python': sys.version, 'worker_packages': packages,
                'protocol': 'UPSTREAM_RETRIEVAL_COMMON_READER_QA_NOT_NATIVE_QA'}

    def retrieve(self, request, k):
        # Identical dated/authority filtering is applied in parent after mapping.
        query = request['question']
        before = self.calls
        if self.cfg['method'] == 'lightrag':
            raw = self.loop.run_until_complete(self.engine.aquery_data(query,
                param=self.query_param(mode='hybrid', top_k=k, chunk_top_k=k)))
            if raw.get('status') != 'success':
                raise ValueError('LightRAG retrieval did not succeed')
            chunks = raw.get('data', {}).get('chunks', [])
            ids = []
            unmapped = 0
            for chunk in chunks:
                uid = chunk.get('file_path')
                content = chunk.get('content', '')
                # Mapping requires actual extracted source content, not a
                # generated entity summary or an embedding nearest neighbour.
                if uid not in self.tagged_by_id or not content.strip() or content not in self.tagged_by_id[uid]:
                    unmapped += 1
                    continue
                if uid not in ids: ids.append(uid)
            calls = self.calls - before
        else:
            values = self.engine.retrieve([query], num_to_retrieve=k)
            if isinstance(values, tuple): values = values[0]
            docs = values[0].docs
            ids = [self.reverse[text] for text in docs if text in self.reverse]
            unmapped = sum(text not in self.reverse for text in docs)
            calls = None  # Upstream OpenIE/retrieval calls not instrumented by us.
        if unmapped:
            raise ValueError('Native source mapping incomplete; no approximate qrel matching allowed')
        return {'status': 'OK', 'retrieved_ids': list(dict.fromkeys(ids)), 'llm_calls': calls,
                'component_exposure': {'native_method': self.cfg['method'], 'retrieval_llm_calls': calls},
                'retrieval_protocol': 'NATIVE_GRAPH_RETRIEVAL_CANONICAL_UNIT_MAPPING'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--config', required=True)
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
    class RedactedLog:
        def __init__(self, stream):
            self.stream = stream
            names = [cfg.get('llm_api_key_env', 'BASELINE_API_KEY'), cfg.get('embedding_api_key_env', 'BASELINE_API_KEY'),
                     'GEMINI_API_KEY', 'HF_TOKEN']
            self.secrets = [os.environ[n] for n in names if os.environ.get(n) and len(os.environ[n]) >= 8]
        def write(self, text):
            for secret in self.secrets:
                text = text.replace(secret, '[REDACTED]')
            return self.stream.write(text)
        def flush(self):
            self.stream.flush()
        def isatty(self):
            return False
    sys.stderr = RedactedLog(sys.stderr)
    # No arbitrary factory import or pickle loading. Redirect upstream print()
    # to stderr so JSONL protocol cannot be confused with progress output.
    native = None
    for line in sys.stdin:
        try:
            command = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if command['action'] == 'prepare':
                    native = Native(cfg); result = native.prepare()
                elif command['action'] == 'retrieve' and native:
                    result = native.retrieve(command['request'], command['k'])
                else:
                    raise ValueError('Invalid protocol action')
        except Exception as exc:
            # SDK messages can contain credentials. Expose type only.
            result = {'status': 'ERROR', 'error_type': type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
