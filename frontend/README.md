# VN Labor Legal RAG frontend

Frontend React/Vite calls the ONLINE API through the Vite `/api` proxy.

From the project root, start the API in the first terminal:

```bat
run.bat online
```

Start the frontend in a second terminal:

```bat
run.bat frontend
```

Open the Vite URL, normally `http://127.0.0.1:5173`. The API runs at
`http://127.0.0.1:8000`; Swagger is available at `/docs`.

To use another API address, copy `frontend/.env.example` to `frontend/.env`
and change `VITE_BACKEND_TARGET`.

The UI preserves the API states `SUFFICIENT`, `PARTIAL_ALLOWED`,
`NEED_MORE_FACTS`, and `INSUFFICIENT_EVIDENCE`. Citation markers map to
`evidence_id` values and open the source drawer.
