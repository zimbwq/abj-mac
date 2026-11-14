import unittest
from unittest.mock import Mock

from cloud_backend import Session
from credentials import CredentialStore


class MemoryKeychain:
    def __init__(self):
        self.items = {}

    def set_password(self, service, account, value):
        self.items[service, account] = value

    def get_password(self, service, account):
        return self.items.get((service, account))

    def delete_password(self, service, account):
        del self.items[service, account]


class CredentialTests(unittest.TestCase):
    def test_restore_after_recreating_store_and_replace_provider(self):
        backend = MemoryKeychain()
        for session in (Session('Gemini', 'test-google', 'custom-gemini'),
                        Session('OpenAI', 'test-openai', 'custom-openai')):
            CredentialStore(backend).save(session)
            self.assertEqual(CredentialStore(backend).load(), session)
        self.assertEqual(len(backend.items), 1)

    def test_delete_and_first_launch(self):
        backend = MemoryKeychain()
        store = CredentialStore(backend)
        self.assertIsNone(store.load())
        store.delete()
        store.save(Session('Gemini', 'test'))
        store.delete()
        self.assertIsNone(CredentialStore(backend).load())

    def test_errors_do_not_expose_credentials(self):
        for method in ('load', 'save', 'delete'):
            backend = Mock()
            backend.get_password.side_effect = Exception('secret')
            backend.set_password.side_effect = Exception('secret')
            with self.assertRaises(RuntimeError) as caught:
                fn = getattr(CredentialStore(backend), method)
                fn(Session('Gemini', 'secret')) if method == 'save' else fn()
            self.assertNotIn('secret', str(caught.exception))

    def test_corrupt_data_rejected(self):
        for value in ('bad json', '{}', '{"provider":"other","key":"secret","model":"m"}'):
            backend = Mock()
            backend.get_password.return_value = value
            with self.assertRaises(RuntimeError):
                CredentialStore(backend).load()

    def test_selftest_service_is_isolated(self):
        backend = MemoryKeychain()
        store = CredentialStore(backend)
        session = Session('Gemini', 'test')
        store.save(session)
        test_store = CredentialStore(backend, service='isolated-test')
        self.assertIsNone(test_store.load())
        test_store.delete()
        self.assertEqual(store.load(), session)
