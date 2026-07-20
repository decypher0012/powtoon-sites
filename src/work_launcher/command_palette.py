from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class CommandPalette(tk.Toplevel):
    def __init__(self, master, commands: dict[str, Callable[[], None]]):
        super().__init__(master)
        self.title("Work Launcher Commands")
        self.geometry("520x360")
        self.transient(master)
        self.commands = commands
        self.query = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.query)
        entry.pack(fill="x", padx=12, pady=12)
        self.listbox = tk.Listbox(self, activestyle="dotbox")
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.query.trace_add("write", lambda *_: self.refresh())
        self.listbox.bind("<Double-Button-1>", self.execute)
        self.bind("<Return>", self.execute)
        self.bind("<Escape>", lambda _: self.destroy())
        self.refresh()
        entry.focus_set()

    def refresh(self) -> None:
        needle = self.query.get().strip().casefold()
        self.listbox.delete(0, "end")
        for label in self.commands:
            if needle in label.casefold():
                self.listbox.insert("end", label)
        if self.listbox.size():
            self.listbox.selection_set(0)

    def execute(self, _event=None) -> None:
        selected = self.listbox.curselection()
        if not selected:
            return
        label = self.listbox.get(selected[0])
        action = self.commands[label]
        self.destroy()
        action()
