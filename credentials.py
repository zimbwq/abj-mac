"""Persist the last selected session exclusively in the macOS Keychain."""
import json

from cloud_backend import Session

SERVICE = 'io.github.zimbwq.abjmac'
ACCOUNT = 'saved-session'


class CredentialStore:
    def __init__(self, backend=None, service=SERVICE):
        if backend is None:
            # Explicit backend: never use environment-selected or plaintext backends.
            from keyring.backends.macOS import Keyring
            backend = Keyring()
        self.backend = backend
        self.service = service

    def load(self):
        try:
            value = self.backend.get_password(self.service, ACCOUNT)
            if value is None:
                return None
            data = json.loads(value)
            return Session(data['provider'], data['key'], data['model'])
        except Exception:
            raise RuntimeError('Не удалось прочитать настройки из Связки ключей macOS. '
                               'Проверьте доступ или введите ключ заново.') from None

    def save(self, session):
        try:
            self.backend.set_password(self.service, ACCOUNT, json.dumps({
                'provider': session.provider, 'key': session.key, 'model': session.model}))
        except Exception:
            raise RuntimeError('Не удалось сохранить ключ в Связке ключей macOS. '
                               'Настройки не изменены. Проверьте доступ и повторите.') from None

    def delete(self):
        try:
            if self.backend.get_password(self.service, ACCOUNT) is not None:
                self.backend.delete_password(self.service, ACCOUNT)
        except Exception:
            raise RuntimeError('Не удалось удалить сохранённый ключ. Проверьте доступ '
                               'к Связке ключей macOS и повторите.') from None
