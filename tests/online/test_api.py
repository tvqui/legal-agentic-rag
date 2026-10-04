from __future__ import annotations
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi.testclient import TestClient
from vn_labor_online.api import create_app
from vn_labor_online.config import OnlineConfig, RetrievalConfig, GraphConfig

try:
    from .test_online_core import fixture
except Exception:
    try:
        from test_online_core import fixture
    except Exception:
        from tests.online.test_online_core import fixture

class TestApiErrorHandling(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict('os.environ', {
            'VN_LABOR_ARTIFACT_SOURCE': '',
            'VN_LABOR_ONLINE_CACHE': '',
            'VN_LABOR_APPLICABILITY_MODE': 'deterministic',
            'VN_LABOR_ADJUDICATION_MODE': 'deterministic',
            'VN_LABOR_API_KEY': '',
        }, clear=False)
        self.env_patcher.start()
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.build = fixture(self.root)
        self.cfg = OnlineConfig(
            artifact_source=str(self.root),
            expected_build_id=self.build,
            cache_dir=str(self.root / 'cache'),
            trace_dir=str(self.root / 'traces'),
            retrieval=RetrievalConfig(dense_enabled=False),
            graph=GraphConfig(max_nodes=3, max_edges=3, max_hops=2, max_rounds=2),
        )
        self.config_path = self.root / 'online.json'
        self.config_path.write_text(json.dumps({'online': self.cfg.model_dump(mode='json')}), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()
        self.env_patcher.stop()

    def test_validation_error_returns_structured_envelope(self):
        with TestClient(create_app(self.config_path)) as client:
            res = client.post('/v1/answer', json={'question': 'Nghỉ việc', 'query_date': 'invalid-date-format'})
            self.assertEqual(res.status_code, 422)
            body = res.json()
            self.assertEqual(body['status'], 'error')
            self.assertTrue(body['error_id'].startswith('ERR_'))
            self.assertEqual(body['category'], 'VALIDATION_ERROR')
            self.assertIn('message', body)
            self.assertIn('errors', body['details'])

    def test_auth_failure_returns_structured_envelope(self):
        with patch.dict('os.environ', {'VN_LABOR_API_KEY': 'secret-123'}, clear=False):
            with TestClient(create_app(self.config_path)) as client:
                res = client.get('/ready')
                self.assertEqual(res.status_code, 401)
                body = res.json()
                self.assertEqual(body['status'], 'error')
                self.assertEqual(body['category'], 'UNAUTHORIZED')
                self.assertTrue(body['error_id'].startswith('ERR_'))

    def test_service_unavailable_returns_structured_envelope(self):
        # Empty config causing pipeline init failure
        bad_config = self.root / 'bad.json'
        bad_config.write_text(json.dumps({'online': {'artifact_source': 'non_existent_path'}}), encoding='utf-8')
        with TestClient(create_app(bad_config)) as client:
            res = client.get('/ready')
            self.assertEqual(res.status_code, 503)
            body = res.json()
            self.assertEqual(body['status'], 'error')
            self.assertEqual(body['category'], 'SERVICE_UNAVAILABLE')

if __name__ == '__main__':
    unittest.main()
