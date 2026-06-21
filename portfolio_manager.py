from postgres_storage import DatabaseUnavailable, PortfolioRepository


class PortfolioManager:
    @staticmethod
    def _safe(email):
        return email.replace("@", "_").replace(".", "_")

    @staticmethod
    def get_path(email):
        return f"postgresql://portfolio/{PortfolioManager._safe(email)}"

    @staticmethod
    def load(email):
        try:
            data = PortfolioRepository.load(email)
            print(f"[PortfolioManager] Загружено {len(data)} позиций для {email} из PostgreSQL")
            return data
        except DatabaseUnavailable as e:
            print(f"[PortfolioManager] {e}")
            return []
        except Exception as e:
            print(f"[PortfolioManager] Ошибка загрузки из PostgreSQL: {e}")
            return []

    @staticmethod
    def save(email, portfolio):
        try:
            PortfolioRepository.save(email, portfolio)
            print(f"[PortfolioManager] Портфель {email} сохранен в PostgreSQL")
            return True
        except DatabaseUnavailable as e:
            print(f"[PortfolioManager] {e}")
            return False
        except Exception as e:
            print(f"[PortfolioManager] Ошибка сохранения в PostgreSQL: {e}")
            return False
