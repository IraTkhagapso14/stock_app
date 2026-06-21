
import hashlib
import secrets
from typing import Dict, Optional

from postgres_storage import DatabaseUnavailable, UserRepository


class UserManager:
    def __init__(self, storage_path: str = "users.json"):
        self.storage_path = storage_path

    @staticmethod
    def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(16)
        salted = password + salt
        hash_obj = hashlib.sha256(salted.encode("utf-8"))
        return hash_obj.hexdigest(), salt

    def register(self, email: str, password: str, name: str) -> tuple[bool, str]:
        try:
            password_hash, salt = self._hash_password(password)
            created = UserRepository.create_user(email, name, password_hash, salt)
        except DatabaseUnavailable as e:
            return False, str(e)

        if not created:
            return False, "Пользователь с таким email уже существует"
        return True, "Регистрация успешна"

    def authenticate(self, email: str, password: str) -> tuple[bool, Optional[str]]:
        try:
            user_data = UserRepository.get_user(email)
        except DatabaseUnavailable as e:
            print(f"[UserManager] {e}")
            return False, None

        if not user_data:
            return False, None

        salt = user_data["salt"]
        expected_hash = user_data["password_hash"]
        input_hash, _ = self._hash_password(password, salt)

        if input_hash == expected_hash:
            return True, user_data["name"]
        return False, None

    def get_profile(self, email: str) -> Optional[Dict]:
        try:
            return UserRepository.get_user(email)
        except DatabaseUnavailable as e:
            print(f"[UserManager] {e}")
            return None
