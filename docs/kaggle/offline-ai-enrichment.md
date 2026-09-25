# Chạy OFFLINE AI enrichment trên Kaggle

Không cần OCR hay dựng Dense lại từ đầu. Dùng package code mới và checkpoint `vn_labor_results_v8.1(aura).zip`.

1. Build/upload `build/kaggle/vn_labor_kaggle_v8.zip` thành Dataset Private và gắn checkpoint V8.1 làm Input thứ hai.
2. Mở notebook V8, đặt `RUN_PIPELINE=False`, `LOAD_AURA=False`, `RESTORE_ARCHIVE="AUTO"`; chạy cell bootstrap để có `ROOT` và `PYTHON`.
3. Với Qwen miễn phí trên Kaggle, chạy:

```python
import os, subprocess, time
subprocess.run('curl -fsSL https://ollama.com/install.sh | sh', shell=True, check=True)
ollama_env=dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', CUDA_VISIBLE_DEVICES='1')
ollama_log=open('/kaggle/working/ollama-offline.log','w')
ollama=subprocess.Popen(['ollama','serve'],env=ollama_env,stdout=ollama_log,stderr=subprocess.STDOUT)
time.sleep(5)
subprocess.run(['ollama','pull','qwen3:8b'],env=ollama_env,check=True)
os.environ.update(VN_LABOR_OFFLINE_AI_PROVIDER='ollama',
                  VN_LABOR_OFFLINE_AI_URL='http://127.0.0.1:11434/api/chat',
                  VN_LABOR_OFFLINE_AI_MODEL='qwen3:8b')
subprocess.run([str(PYTHON),'kaggle/offline_ai_remote.py'],cwd=ROOT,check=True)
```

4. Kiểm `artifacts/reports/tong_hop_sau_chay.md`. Nếu graph hợp lệ, nạp build mới lên Aura bằng cách chạy lại lệnh cuối với `--load-aura` sau khi đã cấp bốn Neo4j Secrets.
5. Tải `/kaggle/working/vn_labor_results.zip`. Không dùng `neo4j_validation.json` cũ vì enrichment làm graph build ID thay đổi.

Muốn dùng API OpenAI-compatible, tạo Kaggle Secret cho API key rồi đặt `VN_LABOR_OFFLINE_AI_PROVIDER=http`, URL, model và `VN_LABOR_OFFLINE_AI_API_KEY`. Chế độ `hybrid_ai` chỉ gọi model khi heuristic chưa tạo được checklist, có cache nên chạy lại không gọi lại record đã hoàn tất.
