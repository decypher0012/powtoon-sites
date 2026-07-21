from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk


def create_nav_icon(name: str):
    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0)); draw = ImageDraw.Draw(image); color = "#d9fffa"
    if name == "Dashboard":
        for box in ((2, 2, 8, 8), (10, 2, 16, 8), (2, 10, 8, 16), (10, 10, 16, 16)): draw.rectangle(box, outline=color, width=2)
    elif name == "Workspaces": draw.rectangle((2, 5, 16, 15), outline=color, width=2); draw.line((6, 5, 7, 2, 12, 2, 13, 5), fill=color, width=2)
    elif name == "Launch history": draw.ellipse((2, 2, 16, 16), outline=color, width=2); draw.line((9, 5, 9, 10, 13, 12), fill=color, width=2)
    elif name == "Repair center": draw.ellipse((3, 3, 15, 15), outline=color, width=2); draw.line((6, 12, 12, 6), fill=color, width=2)
    else: draw.ellipse((5, 5, 13, 13), outline=color, width=2); draw.rectangle((8, 1, 10, 5), fill=color); draw.rectangle((8, 13, 10, 17), fill=color)
    return ImageTk.PhotoImage(image)


class ScheduleDiagnosticsDialog(tk.Toplevel):
    def __init__(self, master, rows, repair):
        super().__init__(master); self.title("Schedule Diagnostics"); self.geometry("760x420"); self.transient(master)
        tree = ttk.Treeview(self, columns=("registered", "status", "last", "next"), show="tree headings")
        for column, label in (("#0", "Schedule"), ("registered", "Registered"), ("status", "Status"),
                              ("last", "Last run"), ("next", "Next run")): tree.heading(column, text=label)
        for row in rows: tree.insert("", "end", text=row["name"], values=(row["registered"], row["status"], row["last_run"], row["next_run"]))
        tree.pack(fill="both", expand=True, padx=14, pady=14)
        buttons = ttk.Frame(self, padding=(14, 0, 14, 14)); buttons.pack(fill="x")
        ttk.Button(buttons, text="Repair Tasks", command=lambda: self._repair(repair), style="Primary.TButton").pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

    def _repair(self, repair):
        errors = repair()
        messagebox.showerror(self.title(), "\n".join(errors), parent=self) if errors else messagebox.showinfo(self.title(), "Scheduled tasks repaired.", parent=self)
        self.destroy()
