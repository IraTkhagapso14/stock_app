import tkinter as tk

BG = "#F5F5F7"
CARD = "#FFFFFF"
PRIMARY = "#007AFF"
TEXT = "#1D1D1F"
SUBTEXT = "#6E6E73"
BORDER = "#E5E5EA"

FONT_TITLE = ("SF Pro Display", 20, "bold")
FONT_BODY = ("SF Pro Text", 12)
FONT_SMALL = ("SF Pro Text", 10)


def create_card(parent):
    frame = tk.Frame(parent, bg=CARD, bd=0)
    frame.pack(fill="x", padx=20, pady=10)
    frame.configure(highlightbackground=BORDER, highlightthickness=1)
    return frame


def primary_button(parent, text, command):
    return tk.Button(parent,
                     text=text,
                     command=command,
                     bg=PRIMARY,
                     fg="white",
                     bd=0,
                     padx=16,
                     pady=10,
                     font=("SF Pro Text", 12, "bold"),
                     cursor="hand2",
                     activebackground="#005FCC")


def input_field(parent, placeholder):
    entry = tk.Entry(parent,
                     bd=0,
                     font=("SF Pro Text", 12),
                     bg="#F2F2F7",
                     fg="#8E8E93",
                     relief="flat")

    entry.insert(0, placeholder)
    entry.pack(fill="x", padx=20, pady=10, ipady=10)

    def on_focus_in(e):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=TEXT)

    def on_focus_out(e):
        if entry.get() == "":
            entry.insert(0, placeholder)
            entry.config(fg="#8E8E93")

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)

    return entry