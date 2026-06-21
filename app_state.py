from profile_manager import ProfileManager

class AppState:
    def __init__(self):
        self.user = None
        self.email = None
        self.is_guest = False
        self.portfolio = []
        self.profile = {
            "display_name": "",
            "email": "",
            "avatar_letter": "",
            "favorites": [],
            "recently_viewed": [],
            "notifications": {
                "price_alerts": True,
                "news_digest": False,
                "ipo_reminders": True,
                "email_notifications": False
            },
            "theme": "dark",
            "language": "ru",
            "auth_token": "",
            "gigachat_auth_key": ""
        }

    def set_user(self, name, email, is_guest=False):
        # Сохраняем старый ключ AI (на случай, если он был)
        old_key = self.profile.get("gigachat_auth_key", "")
        self.user = name
        self.email = email
        self.is_guest = is_guest
        user_data = ProfileManager.get_user_data(email)
        self.profile = user_data["profile"]
        self.portfolio = user_data["portfolio"]
        self.profile["display_name"] = name
        self.profile["email"] = email
        self.profile["avatar_letter"] = name[0].upper() if name else "U"
        # Восстанавливаем ключ AI, если он был передан ранее
        if not self.profile.get("gigachat_auth_key") and old_key:
            self.profile["gigachat_auth_key"] = old_key
        self.save()
        print(f"[AppState] Пользователь {email}")

    def save(self):
        if self.email:
            ProfileManager.save_user_data(self.email, self.profile, self.portfolio)
        else:
            print("[AppState] Нельзя сохранить: email не задан")


class ThemeManager:
    _theme = "dark"
    _listeners = []
    @classmethod
    def get_theme(cls): return cls._theme
    @classmethod
    def set_theme(cls, theme):
        if theme != cls._theme:
            cls._theme = theme
            for cb in cls._listeners: cb(theme)
    @classmethod
    def subscribe(cls, cb): cls._listeners.append(cb)

class LanguageManager:
    _lang = "ru"
    _listeners = []
    @classmethod
    def get_lang(cls): return cls._lang
    @classmethod
    def set_lang(cls, lang):
        if lang != cls._lang:
            cls._lang = lang
            for cb in cls._listeners: cb(lang)
    @classmethod
    def subscribe(cls, cb): cls._listeners.append(cb)

app_state = AppState()