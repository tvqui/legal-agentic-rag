# Next steps — làm nhanh OFFLINE

1. Double-click `RUN_0_SETUP_FULL.bat`.
2. Double-click `RUN_ALL_OFFLINE.bat`.
3. Mở `artifacts/reports/summary.md` và `validation_issues.jsonl`.
4. Sửa metadata còn `UNKNOWN` trong `config/metadata_overrides.yaml`, rồi chạy lại `RUN_ALL_OFFLINE.bat`.
5. Optional: chạy `RUN_ENRICH_OLLAMA.bat` để nâng Diagnostic Checklist.
6. Chạy `RUN_NEO4J.bat` rồi `RUN_LOAD_NEO4J.bat`.
7. Khi Graph + Dense + BM25 đều có output và validation không còn ERROR cấu trúc, coi OFFLINE v1 hoàn tất và chuyển sang ONLINE.
