import tkinter as tk
from app_state import app_state
from dashboard import DashboardScreen
from screens.splash import SplashScreen
from screens.onboarding import OnboardingScreen
from screens.auth import AuthScreen
import os
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        try:
            self.tk.eval('encoding system utf-8')
        except:
            pass
        self.withdraw()
        print("[DEBUG] App initialized, starting start_app")
        self.after(100, self.start_app)

    def start_app(self):
        print("[DEBUG] start_app called")
        splash = SplashScreen(self)
        print("[DEBUG] SplashScreen created")
        self.wait_window(splash)
        print("[DEBUG] SplashScreen closed")

        onboarding = OnboardingScreen(self)
        print("[DEBUG] OnboardingScreen created")
        self.wait_window(onboarding)
        print("[DEBUG] OnboardingScreen closed")

        
        auth = AuthScreen(self)
        print("[DEBUG] AuthScreen created")
        self.wait_window(auth)
        print("[DEBUG] AuthScreen closed")

        
        if app_state.user and app_state.email:
            print(f"[DEBUG] User logged in: {app_state.user} ({app_state.email})")
            dashboard = DashboardScreen(self, username=app_state.user)
            dashboard.protocol("WM_DELETE_WINDOW", self._on_dashboard_close)
            self.withdraw()  
        else:
            print("[DEBUG] No user logged in, quitting")
            self.quit()

    def _on_dashboard_close(self):
        print("[DEBUG] Dashboard closed, quitting app")
        self.quit()

if __name__ == "__main__":
    app = App()
    app.mainloop()