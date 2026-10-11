"""Mega Zword usage widget: a small always-on-top window showing every AI's plan usage.

Run with: .venv\\Scripts\\pythonw scripts\\usage_widget.pyw   (or the desktop shortcut)
Refreshes every 2 minutes (click to refresh now). Drag to move, right-click to close.
Reads the same meters as `megazword usage`; never calls a model.
"""

import threading
import tkinter as tk
from datetime import datetime, timezone

from megazword import config, usage_sources

REFRESH_MS = 120_000
BG, FG, DIM, ACCENT, WARN, BAD = "#14161a", "#e6e6e6", "#8a8f98", "#3ddc84", "#f5c542", "#ff5c5c"
NAMES = {"claude": "Claude", "codex": "Codex", "grok": "Grok", "gemini": "Gemini"}
FONT = ("Cascadia Code", 10)
SMALL = ("Cascadia Code", 8)


def color(p):
    return BAD if p >= 90 else WARN if p >= 70 else ACCENT


def until(dt):
    if not dt:
        return ""
    secs = (dt - datetime.now(timezone.utc)).total_seconds()
    if secs <= 0:
        return "now"
    h = secs / 3600
    return f"{h:.0f}h" if h < 48 else f"{h / 24:.0f}d"


class Widget:
    def __init__(self, root):
        self.root = root
        root.title("MZ usage")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry("+40+40")
        self.frame = tk.Frame(root, bg=BG, padx=10, pady=8)
        self.frame.pack()
        self.status = tk.Label(self.frame, text=">_ reading meters...", bg=BG, fg=DIM, font=SMALL)
        self.status.grid(row=99, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for w in (root, self.frame):
            w.bind("<ButtonPress-1>", self.start_drag)
            w.bind("<B1-Motion>", self.drag)
            w.bind("<ButtonRelease-1>", self.click)
            w.bind("<Button-3>", lambda e: root.destroy())
        self.moved = False
        self.refresh()

    def start_drag(self, e):
        self.dx, self.dy, self.moved = e.x, e.y, False

    def drag(self, e):
        self.moved = True
        self.root.geometry(f"+{e.x_root - self.dx}+{e.y_root - self.dy}")

    def click(self, e):
        if not self.moved:
            self.refresh(manual=True)

    def refresh(self, manual=False):
        self.status.config(text=">_ reading meters...")
        threading.Thread(target=self.read, daemon=True).start()
        if not manual:
            self.root.after(REFRESH_MS, self.refresh)

    def read(self):
        try:
            plans, out = usage_sources.all_usage(), config.load().out_until
            self.root.after(0, self.draw, plans, out, None)
        except Exception as exc:  # meters are best-effort
            self.root.after(0, self.draw, [], {}, exc)

    def bar(self, row, col, w):
        if w is None:
            tk.Label(self.frame, text="   -   ", bg=BG, fg=DIM, font=FONT).grid(row=row, column=col)
            return
        p = w.used_percent
        filled = max(0, min(8, round(p / 12.5)))
        text = "█" * filled + "░" * (8 - filled)
        cell = tk.Frame(self.frame, bg=BG)
        cell.grid(row=row, column=col, padx=(0, 8), sticky="w")
        tk.Label(cell, text=text, bg=BG, fg=color(p), font=FONT).pack(side="left")
        tk.Label(cell, text=f"{p:3.0f}% {until(w.resets_at):>3}", bg=BG, fg=FG,
                 font=SMALL).pack(side="left", padx=(4, 0))

    def draw(self, plans, out, error):
        for child in self.frame.grid_slaves():
            if child is not self.status:
                child.destroy()
        for col, head in enumerate(("", "5-hour", "week")):
            tk.Label(self.frame, text=head, bg=BG, fg=DIM, font=SMALL).grid(row=0, column=col, sticky="w")
        now = datetime.now(timezone.utc)
        for row, plan in enumerate(plans, start=1):
            tk.Label(self.frame, text=NAMES.get(plan.service, plan.service), bg=BG, fg=FG,
                     font=FONT, width=7, anchor="w").grid(row=row, column=0, sticky="w")
            off = out.get(plan.service)
            if off and off > now:
                tk.Label(self.frame, text=f"OUT for {until(off)}", bg=BG, fg=BAD,
                         font=FONT).grid(row=row, column=1, columnspan=2, sticky="w")
                continue
            five = next((w for w in plan.windows if w.name == "5-hour"), None)
            week = next((w for w in plan.windows if w.name == "weekly"), None)
            if five is None and week is None:
                tk.Label(self.frame, text="no meter", bg=BG, fg=DIM,
                         font=FONT).grid(row=row, column=1, columnspan=2, sticky="w")
                continue
            self.bar(row, 1, five)
            self.bar(row, 2, week)
        stamp = datetime.now().strftime("%I:%M %p").lstrip("0")
        self.status.config(text=f"!! {error}" if error else f">_ {stamp}  click=refresh  right-click=close")


if __name__ == "__main__":
    root = tk.Tk()
    Widget(root)
    root.mainloop()
