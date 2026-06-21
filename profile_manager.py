from postgres_storage import DEFAULT_PROFILE, DatabaseUnavailable, ProfileRepository


class ProfileManager:
    @classmethod
    def _load_all_users(cls):
        raise RuntimeError("JSON-хранилище отключено: данные пользователей находятся в PostgreSQL")

    @classmethod
    def _save_all_users(cls, users_data):
        raise RuntimeError("JSON-хранилище отключено: данные пользователей находятся в PostgreSQL")

    @classmethod
    def get_user_data(cls, user_email):
        try:
            return ProfileRepository.get_user_data(user_email)
        except DatabaseUnavailable as e:
            print(f"[ProfileManager] {e}")
            return {
                "profile": cls._default_profile(user_email),
                "portfolio": [],
            }
        except Exception as e:
            print(f"[ProfileManager] Ошибка загрузки из PostgreSQL: {e}")
            return {
                "profile": cls._default_profile(user_email),
                "portfolio": [],
            }

    @classmethod
    def save_user_data(cls, user_email, profile, portfolio):
        try:
            ProfileRepository.save_user_data(user_email, profile, portfolio)
            print(f"[ProfileManager] Пользователь {user_email} сохранен в PostgreSQL")
        except DatabaseUnavailable as e:
            print(f"[ProfileManager] {e}")
        except Exception as e:
            print(f"[ProfileManager] Ошибка сохранения в PostgreSQL: {e}")

    @classmethod
    def load(cls, default_profile=None):
        return default_profile.copy() if default_profile else {}

    @classmethod
    def save(cls, profile_data):
        print("[ProfileManager] save(profile_data) устарел. Используйте save_user_data().")

    @staticmethod
    def _default_profile(user_email):
        profile = DEFAULT_PROFILE.copy()
        profile["email"] = user_email
        profile["avatar_letter"] = user_email[0].upper() if user_email and user_email != "guest" else "G"
        return profile
