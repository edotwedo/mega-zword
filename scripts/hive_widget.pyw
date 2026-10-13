"""Hive master widget: Phil's always-on-top window into the Hive room (the bots' group chat).

Run with: .venv\\Scripts\\pythonw scripts\\hive_widget.pyw   (or the desktop shortcut)
Type and press Enter to post as Phil; Phil's messages always come first for the bots.
Start runs a few bot turns, Pause stops after the current reply, Stop ends the session.
Drag any bar to move, drag the corner grip to resize; size and spot are remembered. The x closes. Reading the room never calls a model; only Start does.
"""

import json
import subprocess
import sys
import tkinter as tk
from datetime import datetime

from megazword import config, room

POLL_MS = 3000
TURNS = 6
BG, PANEL, FG, DIM, ACCENT, WARN, BAD = "#14161a", "#1d2026", "#e6e6e6", "#8a8f98", "#3ddc84", "#f5c542", "#ff5c5c"
WHO = {"phil": ACCENT, "claude": "#d9a66b", "codex": "#7fb3ff", "grok": "#c792ea", "gemini": "#4fd1c5"}
FONT = ("Cascadia Code", 10)
SMALL = ("Cascadia Code", 8)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MIN_W, MIN_H = 260, 200
SPOT = config.HOME / "hive_widget.json"  # remembered size and position


class HiveWidget:
    def __init__(self, root):
        self.root, self.cfg = root, config.load()
        self.room = self.cfg.room_name or room.DEFAULT_ROOM
        self.seen = None
        root.title("Hive")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry(self.saved_geometry())

        bar = tk.Frame(root, bg=PANEL)
        bar.pack(fill="x")
        self.title = tk.Label(bar, text=f"HIVE · #{self.room}", bg=PANEL, fg=FG, font=FONT, padx=8, pady=4)
        self.title.pack(side="left")
        close = tk.Label(bar, text=" x ", bg=PANEL, fg=DIM, font=FONT, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.close())

        self.log = tk.Text(root, bg=BG, fg=FG, font=FONT, wrap="word", bd=0, padx=8, pady=6,
                           state="disabled", height=18)
        self.log.pack(fill="both", expand=True)
        for name, col in WHO.items():
            self.log.tag_config(name, foreground=col, font=(FONT[0], FONT[1], "bold"))
        self.log.tag_config("dim", foreground=DIM, font=SMALL)

        self.entry = tk.Entry(root, bg=PANEL, fg=FG, insertbackground=FG, font=FONT, bd=0,
                              relief="flat")
        self.entry.pack(fill="x", padx=6, pady=(4, 2), ipady=5)
        self.entry.bind("<Return>", self.send)
        self.entry.focus_set()

        ctl = tk.Frame(root, bg=BG)
        ctl.pack(fill="x", padx=6, pady=(2, 6))
        for text, cmd in (("▶ Start", self.start), ("⏸ Pause", self.pause), ("■ Stop", self.stop)):
            b = tk.Label(ctl, text=text, bg=PANEL, fg=FG, font=SMALL, padx=8, pady=3, cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, c=cmd: c())
        grip = tk.Label(ctl, text="◢", bg=BG, fg=DIM, font=FONT, cursor="size_nw_se")
        grip.pack(side="right")
        grip.bind("<ButtonPress-1>", self.start_resize)
        grip.bind("<B1-Motion>", self.resize)
        self.status = tk.Label(ctl, text="", bg=BG, fg=DIM, font=SMALL)
        self.status.pack(side="right", padx=(0, 6))
        for w in (bar, self.title, ctl, self.status):  # move by dragging any bar
            w.bind("<ButtonPress-1>", self.start_drag, add="+")
            w.bind("<B1-Motion>", self.drag, add="+")
        root.bind("<Escape>", lambda e: self.close())
        self.poll()

    def saved_geometry(self):
        try:
            g = json.loads(SPOT.read_text(encoding="utf-8"))["geometry"]
            return g if isinstance(g, str) else "380x460+40+260"
        except (OSError, ValueError, KeyError, TypeError):
            return "380x460+40+260"

    def close(self):
        try:
            SPOT.parent.mkdir(parents=True, exist_ok=True)
            SPOT.write_text(json.dumps({"geometry": self.root.geometry()}), encoding="utf-8")
        except OSError:
            pass
        self.root.destroy()

    def start_resize(self, e):
        self.rx, self.ry = e.x_root, e.y_root
        self.rw, self.rh = self.root.winfo_width(), self.root.winfo_height()

    def resize(self, e):
        w = max(MIN_W, self.rw + e.x_root - self.rx)
        h = max(MIN_H, self.rh + e.y_root - self.ry)
        self.root.geometry(f"{w}x{h}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def start_drag(self, e):
        # Offset from the window corner, not the clicked label, so no jump when grabbing a label.
        self.dx, self.dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def drag(self, e):
        self.root.geometry(f"+{e.x_root - self.dx}+{e.y_root - self.dy}")

    def note(self, text, color=DIM):
        self.status.config(text=text, fg=color)

    def send(self, _event=None):
        text = self.entry.get().strip()
        if not text:
            return
        try:
            room.say(self.room, text, author="phil", write=lambda s: None)
            self.entry.delete(0, "end")
        except Exception as exc:
            self.note(f"!! {exc}", BAD)
        self.poll(once=True)

    def start(self):
        state = room.load_state(self.room)
        if room.other_session_running(state):
            self.note("already running", WARN)
            return
        code = "import sys; from megazword.cli import main; sys.exit(main(sys.argv[1:]))"
        subprocess.Popen([sys.executable, "-c", code, "room", "start", "--room", self.room,
                          "--turns", str(TURNS)], creationflags=NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.note(f"starting {TURNS} turns...", ACCENT)

    def pause(self):
        room.set_paused(self.room, True)
        self.note("pausing after this reply", WARN)

    def stop(self):
        room.set_stopped(self.room)
        self.note("stopping", BAD)

    def poll(self, once=False):
        try:
            messages = room.read_messages(self.room)
            state = room.load_state(self.room)
            key = (len(messages), messages[-1].time if messages else None)
            if key != self.seen:
                self.seen = key
                self.draw(messages[-60:])
            if room.other_session_running(state) and not state.paused:
                self.note(f"live · turn {state.turn_count}/{state.turn_cap}", ACCENT)
            elif self.status.cget("fg") not in (WARN, BAD) or not once:
                self.note(f"idle · {datetime.now().strftime('%I:%M %p').lstrip('0')}")
        except Exception as exc:
            self.note(f"!! {exc}", BAD)
        if not once:
            self.root.after(POLL_MS, self.poll)

    def draw(self, messages):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        for m in messages:
            self.log.insert("end", m.author, m.author if m.author in WHO else "dim")
            self.log.insert("end", f"  {m.time[11:16]}\n", "dim")
            self.log.insert("end", m.text.strip() + "\n\n")
        self.log.config(state="disabled")
        self.log.see("end")


if __name__ == "__main__":
    root = tk.Tk()
    HiveWidget(root)
    root.mainloop()
