from __future__ import annotations


class CredentialStore:
    service_name = "subreplace-studio"

    def load(self, provider: str) -> str:
        try:
            import keyring
            return keyring.get_password(self.service_name, provider) or ""
        except Exception:
            return ""

    def save(self, provider: str, api_key: str) -> bool:
        try:
            import keyring
            keyring.set_password(self.service_name, provider, api_key)
            return True
        except Exception:
            return False

    def delete(self, provider: str) -> None:
        try:
            import keyring
            keyring.delete_password(self.service_name, provider)
        except Exception:
            pass
