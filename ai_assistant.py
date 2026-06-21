import tkinter as tk
import threading
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEFAULT_GIGACHAT_AUTH_KEY
from gigachat import GigaChat
from gigachat.models import Chat

from dashboard import (
    BG, SURFACE, SURFACE2, ACCENT,
    ACCENT2, TEXT_PRI, TEXT_SEC, WHITE, BORDER
)
from app_state import app_state

SYSTEM_PROMPT = (
    "Ты — AI-ассистент финансового приложения StockAI Pro. "
    "Помогаешь пользователям разбираться в акциях, рынках, IPO и инвестициях. "
    "Отвечай на русском языке кратко и по делу."
)

def get_gigachat_key():
    user_key = app_state.profile.get("gigachat_auth_key", "").strip()

    if user_key:
        return user_key

    return DEFAULT_GIGACHAT_AUTH_KEY

def set_gigachat_key(key):
    """Сохраняет ключ GigaChat в app_state.profile и выполняет save."""
    app_state.profile["gigachat_auth_key"] = key
    app_state.save()

def get_gigachat_response(conversation_history):
    auth_key = get_gigachat_key()
    if not auth_key:
        return "❌ Ключ авторизации GigaChat не найден. Добавьте его в настройках профиля (⚙️)."
    try:
        giga = GigaChat(credentials=auth_key, verify_ssl_certs=False)
        messages = []
        for msg in conversation_history:
            role = "user" if msg["role"] == "user" else "assistant"
            content = msg["parts"][0]["text"]
            messages.append({"role": role, "content": content})
        chat = Chat(messages=messages)
        response = giga.chat(chat)
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка GigaChat: {e}"

def get_ai_response(conversation_history):
    return get_gigachat_response(conversation_history)

class AIAssistantPage(tk.Frame):
    def __init__(self, parent, dashboard_ref):
        super().__init__(parent, bg=BG)
        self.dashboard = dashboard_ref
        self.is_waiting = False
        self.conversation_history = []
        self._build_ui()
        self._add_welcome_message()

    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=20, pady=(20, 10))
        tk.Label(header, text="🤖 AI Ассистент", font=("Helvetica", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")


        clear_btn = tk.Button(header, text="🗑 Очистить", command=self._clear_chat,
                              bg=SURFACE, fg=TEXT_SEC, bd=0, cursor="hand2")
        clear_btn.pack(side="right")

        chat_container = tk.Frame(self, bg=BG)
        chat_container.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self.canvas = tk.Canvas(chat_container, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(chat_container, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.messages_frame = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.messages_frame, anchor="nw")

        self.messages_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel()

        input_frame = tk.Frame(self, bg=BG)
        input_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.input_entry = tk.Text(input_frame, height=3, font=("Helvetica", 11),
                                   bg=SURFACE, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                                   relief="flat")
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.input_entry.bind("<Return>", self._on_enter)
        self.input_entry.bind("<Shift-Return>", self._on_shift_enter)

        send_btn = tk.Button(input_frame, text="➤", command=self.send_message,
                             bg=ACCENT, fg=WHITE, bd=0, padx=12, pady=6, cursor="hand2")
        send_btn.pack(side="right", padx=(10, 0))
        self.input_entry.focus_set()

    def _bind_mousewheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        try:
            if event.delta:
                self.canvas.yview_scroll(int(-event.delta / 60), "units")
            elif event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
        except Exception:
            pass

    def _on_enter(self, event):
        self.send_message()
        return "break"

    def _on_shift_enter(self, event):
        return None

    def _add_message(self, text, is_user=True):
        wrapper = tk.Frame(self.messages_frame, bg=BG)
        wrapper.pack(fill="x", pady=6, padx=10)

        if is_user:
            wrapper.pack(anchor="e")
            bubble_bg = ACCENT
            text_color = WHITE
            anchor = "e"
            padx = (80, 0)
        else:
            wrapper.pack(anchor="w")
            bubble_bg = SURFACE
            text_color = TEXT_PRI
            anchor = "w"
            padx = (0, 80)

        bubble = tk.Frame(wrapper, bg=bubble_bg)
        bubble.pack(anchor=anchor, padx=padx)

        label = tk.Label(bubble, text=text, bg=bubble_bg, fg=text_color,
                         font=("Helvetica", 11), wraplength=500,
                         justify="left", padx=12, pady=8)
        label.pack()
        self.after(10, self._smooth_scroll_to_bottom)

    def _smooth_scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def _add_welcome_message(self):
        key_exists = bool(get_gigachat_key())
        welcome = "Привет! Я помогу с акциями, рынком и инвестициями 📈"
       

    def _clear_chat(self):
        self.conversation_history = []
        for w in self.messages_frame.winfo_children():
            w.destroy()
        self._add_welcome_message()

    def send_message(self):
        if self.is_waiting:
            return
        text = self.input_entry.get("1.0", tk.END).strip()
        if not text:
            return
        self.input_entry.delete("1.0", tk.END)
        self._add_message(text, True)
        self.conversation_history.append({"role": "user", "parts": [{"text": text}]})
        self.is_waiting = True
        threading.Thread(target=self._get_response, args=(list(self.conversation_history),), daemon=True).start()

    def _get_response(self, history_snapshot):
        response = get_ai_response(history_snapshot)
        self.conversation_history.append({"role": "model", "parts": [{"text": response}]})
        self.after(0, lambda: self._add_message(response, False))
        self.after(0, lambda: setattr(self, 'is_waiting', False))

    def refresh(self):
        self._clear_chat()