"""Entry point 2: controlled RAG baselines (Chinese LJP is a separate task)."""
import argparse
import subprocess
import sys
from pathlib import Path
from eval_core import main, dump, sha, environment


def embedding_server(argv):
    """Serve the exact artifact embedding revision to isolated upstream envs."""
    parser = argparse.ArgumentParser(description='Local OpenAI-compatible BGE-M3 endpoint, pinned to artifact weights')
    parser.add_argument('--bundle', required=True); parser.add_argument('--cache', required=True)
    parser.add_argument('--device', default='cpu'); parser.add_argument('--port', type=int, default=8801)
    args = parser.parse_args(argv)
    from eval_core import load_bundle
    manifest, _, _ = load_bundle(args.bundle)
    identity = manifest['embedding_identity']
    if identity['model'] != 'BAAI/bge-m3' or not identity['revision']:
        parser.error('Only a pinned BAAI/bge-m3 artifact is supported by this embedding bridge')
    from huggingface_hub import snapshot_download
    from FlagEmbedding import BGEM3FlagModel
    from fastapi import FastAPI, HTTPException
    import numpy as np
    import uvicorn
    local = snapshot_download(identity['model'], revision=identity['revision'], cache_dir=args.cache)
    encoder = BGEM3FlagModel(local, use_fp16=args.device != 'cpu', devices=args.device)
    app = FastAPI()

    @app.get('/identity')
    def model_identity():
        return {**identity, 'max_length': 1024, 'normalize_l2': True, 'use_fp16': args.device != 'cpu'}

    @app.get('/v1/models')
    def models():
        return {'object': 'list', 'data': [{'id': identity['model'], 'object': 'model', 'owned_by': 'local-pinned-artifact'}]}

    @app.post('/v1/embeddings')
    def embeddings(body: dict):
        texts = body.get('input')
        if isinstance(texts, str): texts = [texts]
        if body.get('model') != identity['model'] or not isinstance(texts, list) or not texts or len(texts) > 128 or any(not isinstance(t, str) for t in texts):
            raise HTTPException(400, 'Need model identity and 1..128 string inputs')
        vectors = np.asarray(encoder.encode(texts, batch_size=min(8, len(texts)), max_length=1024,
            return_dense=True, return_sparse=False, return_colbert_vecs=False)['dense_vecs'], dtype=np.float32)
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        tokenized = encoder.tokenizer(texts, truncation=True, max_length=1024, padding=False)
        token_count = sum(len(ids) for ids in tokenized['input_ids'])
        return {'object': 'list', 'model': identity['model'], 'data': [
            {'object': 'embedding', 'index': i, 'embedding': vector.tolist()} for i, vector in enumerate(vectors)],
            'usage': {'prompt_tokens': token_count, 'total_tokens': token_count}}

    # Binding to loopback is deliberate; the evaluation worker is local.
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
    return 0


def audit_repositories(argv):
    """Read public source/interfaces; do not install or execute upstream code."""
    import urllib.request
    import json
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    parser = argparse.ArgumentParser()
    parser.add_argument('--legal-repo', default='D:/data_thô/legalgraphrag/LegalGraphRAG')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    specs = {
        'lightrag': ('HKUDS/LightRAG', ['lightrag/lightrag.py', 'lightrag/base.py', 'pyproject.toml']),
        'hipporag2': ('OSU-NLP-Group/HippoRAG', ['src/hipporag/HippoRAG.py', 'src/hipporag/utils/config_utils.py', 'pyproject.toml']),
        'graphrag': ('microsoft/graphrag', ['README.md', 'pyproject.toml']),
        'raptor': ('parthsarthi03/raptor', ['raptor/RetrievalAugmentation.py', 'raptor/tree_retriever.py', 'requirements.txt'])}
    notes = {
        'lightrag': 'OPTIONAL_ADAPTER: aquery_data chunks mapped by exact file_path and source content; isolated installation and matched embedding endpoint required; not integration-tested here.',
        'hipporag2': 'OPTIONAL_ADAPTER: index/retrieve QuerySolution.docs exact source mapping; upstream pins torch/transformers, needs a separate venv; not integration-tested here.',
        'graphrag': 'N/A: Microsoft global/local contexts include generated reports/entities. No validated canonical provision mapping or controlled reader integration for this pinned version.',
        'raptor': 'N/A: recursive summary retrieval changes source units; no verified leaf/span mapping back to canonical provisions. A generic tree is NOT the official RAPTOR baseline.'}
    def inspect(entry):
        method, (repo, paths) = entry
        result = {'method': method, 'url': 'https://github.com/' + repo, 'assessment': notes[method]}
        try:
            with urllib.request.urlopen('https://api.github.com/repos/' + repo + '/commits?per_page=1', timeout=30) as response:
                commit = json.load(response)[0]['sha']
            result['commit'] = commit
            result['sources'] = []
            for path in paths:
                url = 'https://raw.githubusercontent.com/' + repo + '/' + commit + '/' + path
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read()
                text = content.decode('utf-8')
                interfaces = [line.strip() for line in text.splitlines() if any(x in line for x in (
                    'def aquery_data(', 'def ainsert(', 'def retrieve(', 'def rag_qa(', 'def index(',
                    'requires-python', '"torch', '"transformers', 'def add_documents('))]
                result['sources'].append({'path': path, 'url': url, 'sha256': hashlib.sha256(content).hexdigest(),
                                          'interfaces_and_requirements': interfaces[:30]})
            result['source_read_status'] = 'PASS_SOURCE_INSPECTION_ONLY'
        except Exception as exc:
            result['source_read_status'] = 'ERROR'; result['error_type'] = type(exc).__name__
        return result
    results = list(ThreadPoolExecutor(4).map(inspect, specs.items()))
    local = Path(args.legal_repo)
    if local.is_dir():
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=local, text=True).strip()
        names = ['README.md', 'requirements.txt', 'core/LegalGraphRAG.py', 'evaluation/evaluate_results.py']
        results.append({'method': 'legalgraphrag_original', 'path': str(local), 'commit': commit,
            'source_sha256': {n: sha(local / n) for n in names},
            'source_read_status': 'PASS_LOCAL_SOURCE_INSPECTION_ONLY',
            'task': 'CHINESE_LJP_CHARGE_ARTICLE_SENTENCE',
            'vietnamese_qa': 'N/A_REQUIRES_NEW_SCHEMA_PROMPTS_RULE_CORPUS_AND_VALIDATED_ADAPTATION',
            'notes': 'ModelConfig accepts en/zh, not vi. analyze_case uses law_to_crime and judge_res. Native China metrics are not Vietnamese QA metrics.'})
    else:
        results.append({'method': 'legalgraphrag_original', 'source_read_status': 'N/A_LOCAL_REPO_NOT_FOUND'})
    dump(args.out, {'inspection_time_environment': environment(), 'repositories': results,
                    'limitations': 'Source inspection is not successful execution or faithful paper reproduction.'})
    print('Saved repository inspection:', args.out)
    return 0 if all(r['source_read_status'].startswith('PASS') for r in results) else 2


def original_ljp(argv):
    parser = argparse.ArgumentParser(description='Use the ORIGINAL upstream LJP scorer, never a Vietnamese QA comparison')
    parser.add_argument('--repo', required=True); parser.add_argument('--results', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    repo, results, out = Path(args.repo).resolve(), Path(args.results).resolve(), Path(args.out).resolve()
    if not results.is_file():
        parser.error('Supply actual original-schema LJP predictions; no generation is fabricated')
    out.mkdir(parents=True, exist_ok=True)
    # Copy predictions before invoking upstream scorer: upstream writes metrics
    # next to its input. No changes to the cloned original repository.
    import shutil
    copied = out / 'ljp_predictions.json'; shutil.copy2(results, copied)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    command = [sys.executable, str(repo / 'evaluation/evaluate_results.py'), '--results', str(copied),
               '--crimes-by-part', str(repo / 'datas/main_experiment/crimes_by_part.json')]
    with (out / 'scorer.log').open('w', encoding='utf-8') as log:
        completed = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    dump(out / 'manifest.json', {'task': 'CHINESE_LEGAL_JUDGMENT_PREDICTION',
         'comparison_to_vietnamese_qa': 'N/A_DIFFERENT_TASK_DATA_LABELS', 'commit': commit,
         'predictions_sha256': sha(copied), 'scorer_sha256': sha(repo / 'evaluation/evaluate_results.py'),
         'environment': environment(), 'exit_code': completed.returncode,
         'note': 'Scoring supplied predictions does not certify reproduction of the paper experiment.'})
    return completed.returncode


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'original-ljp':
        code = original_ljp(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == 'audit-repos':
        code = audit_repositories(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == 'embedding-server':
        code = embedding_server(sys.argv[2:])
    else:
        code = main(baseline=True)
    raise SystemExit(code)
