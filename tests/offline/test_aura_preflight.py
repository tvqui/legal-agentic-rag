import importlib.util
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aura_preflight_tests', ROOT / 'kaggle/aura_preflight.py')
aura = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aura)


class AuraPreflightTests(unittest.TestCase):
    def setUp(self):
        self.env = {'NEO4J_URI': 'neo4j+s://example.databases.neo4j.io',
                    'NEO4J_USER': 'neo4j', 'NEO4J_PASSWORD': 'never-print-this',
                    'NEO4J_DATABASE': 'neo4j'}
        self.resolve = MagicMock(return_value=[('address',)])
        self.sleep = MagicMock()
        self.emit = MagicMock()
        self.factory = MagicMock()
        self.driver = self.factory.return_value.__enter__.return_value
        self.session = self.driver.session.return_value.__enter__.return_value
        self.session.run.return_value.single.return_value = {'ok': 1}

    def check(self, **kwargs):
        return aura.check(self.env, resolve=self.resolve, sleep=self.sleep,
                          driver_factory=self.factory, emit=self.emit, **kwargs)

    def test_success_is_read_only_and_does_not_require_database_equals_instance_id(self):
        result = self.check()
        self.assertTrue(result['passed'])
        self.driver.session.assert_called_once_with(database='neo4j', default_access_mode='READ')
        self.session.run.assert_called_once_with('RETURN 1 AS ok')
        self.assertEqual(len(result['attempts']), 1)
        self.assertNotIn(self.env['NEO4J_PASSWORD'], json.dumps(result))

    def test_dns_failure_is_bounded_and_does_not_connect_driver(self):
        self.resolve.side_effect = socket.gaierror(-2, 'Name or service not known')
        result = self.check()
        self.assertFalse(result['passed'])
        self.assertEqual(result['reason_code'], 'DNS_UNRESOLVED')
        self.assertEqual(self.resolve.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.factory.assert_not_called()

    def test_temporary_dns_failure_recovers_without_false_failure(self):
        self.resolve.side_effect = [socket.gaierror(-3, 'temporary'), [('address',)]]
        result = self.check()
        self.assertTrue(result['passed'])
        self.assertEqual(result['reason_code'], 'PASS')
        self.assertEqual(len(result['attempts']), 2)
        self.sleep.assert_called_once_with(5)

    def test_authentication_failure_is_not_retried_or_echoed(self):
        AuthError = type('AuthError', (Exception,), {})
        self.driver.verify_connectivity.side_effect = AuthError(self.env['NEO4J_PASSWORD'])
        result = self.check()
        self.assertEqual(result['reason_code'], 'AUTH_FAILED')
        self.assertFalse(result['passed'])
        self.sleep.assert_not_called()
        self.assertNotIn(self.env['NEO4J_PASSWORD'], str(self.emit.call_args_list) + json.dumps(result))

    def test_wrong_database_has_separate_diagnostic_and_no_retry(self):
        error = RuntimeError('wrong database')
        error.code = 'Neo.ClientError.Database.DatabaseNotFound'
        self.session.run.side_effect = error
        result = self.check()
        self.assertEqual(result['reason_code'], 'DATABASE_NOT_FOUND')
        self.sleep.assert_not_called()

    def test_invalid_uri_and_missing_secrets_do_not_make_requests(self):
        for uri in ('http://example.com', 'neo4j+s://user:secret@example.com',
                    'neo4j+s://127.0.0.1', 'neo4j+s://example.com:invalid',
                    'neo4j+s://example.com/private', 'neo4j+s://example.com?token=secret'):
            with self.subTest(uri=uri):
                self.env['NEO4J_URI'] = uri
                self.assertEqual(self.check()['reason_code'], 'INVALID_URI')
        self.env['NEO4J_PASSWORD'] = ''
        self.assertEqual(self.check()['reason_code'], 'MISSING_SECRET')
        self.resolve.assert_not_called()
        self.factory.assert_not_called()

    def test_wrapped_dns_failure_and_connection_retry(self):
        wrapped = RuntimeError('wrapper')
        wrapped.__cause__ = socket.gaierror(-2, 'DNS')
        self.assertEqual(aura.reason(wrapped), 'DNS_UNRESOLVED')
        ServiceUnavailable = type('ServiceUnavailable', (Exception,), {})
        self.driver.verify_connectivity.side_effect = [ServiceUnavailable('temporary'), None]
        self.assertTrue(self.check()['passed'])
        self.sleep.assert_called_once_with(5)

    def test_invalid_retry_budget_fails_before_network(self):
        with self.assertRaises(ValueError):
            self.check(attempts=99)
        self.resolve.assert_not_called()
