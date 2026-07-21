from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .constants import DEFAULT_VISUAL_STYLE


VISUAL_PRESETS: dict[str, dict[str, str]] = {
    "enterprise": {
        "bg": "#f0fdfa",
        "card": "#ffffff",
        "surface_alt": "#e6f7f4",
        "sidebar": "#083b3a",
        "sidebar_text": "#d9fffa",
        "text": "#134e4a",
        "muted": "#526b69",
        "primary": "#0d9488",
        "accent": "#c2410c",
        "accent_hover": "#9a3412",
        "accent_active": "#7c2d12",
        "accent_text": "#ffffff",
        "border": "#99d8d1",
        "selection": "#ccfbf1",
        "danger": "#b91c1c",
    },
    "dark": {
        "bg": "#111827",
        "card": "#1f2937",
        "surface_alt": "#263747",
        "sidebar": "#071f22",
        "sidebar_text": "#ccfbf1",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
        "primary": "#2dd4bf",
        "accent": "#fb923c",
        "accent_hover": "#fdba74",
        "accent_active": "#f97316",
        "accent_text": "#111827",
        "border": "#334155",
        "selection": "#1d4ed8",
        "danger": "#f87171",
    },
    "friendly": {
        "bg": "#f9f5ef",
        "card": "#fffdf8",
        "surface_alt": "#f4eadc",
        "sidebar": "#3d2d22",
        "sidebar_text": "#fff7ed",
        "text": "#2b241d",
        "muted": "#6d6257",
        "primary": "#b45309",
        "accent": "#c2410c",
        "accent_hover": "#c26b05",
        "accent_active": "#a85c04",
        "accent_text": "#ffffff",
        "border": "#e7dbc8",
        "selection": "#fde68a",
        "danger": "#b45309",
    },
}


def apply_visual_style(root: tk.Misc, preset: str = DEFAULT_VISUAL_STYLE) -> dict[str, str]:
    palette = VISUAL_PRESETS.get(preset, VISUAL_PRESETS[DEFAULT_VISUAL_STYLE])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=palette["bg"])
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*Background", palette["bg"])
    root.option_add("*Foreground", palette["text"])
    root.option_add("*selectBackground", palette["selection"])
    root.option_add("*selectForeground", palette["text"])
    style.configure(".", background=palette["bg"], foreground=palette["text"])
    style.configure("TFrame", background=palette["bg"])
    style.configure("Card.TFrame", background=palette["card"])
    style.configure("Surface.TFrame", background=palette["surface_alt"])
    style.configure("Sidebar.TFrame", background=palette["sidebar"])
    style.configure("Row.TFrame", background=palette["card"], bordercolor=palette["border"], relief="solid", borderwidth=1)
    style.configure("TLabel", background=palette["bg"], foreground=palette["text"])
    style.configure("Card.TLabel", background=palette["card"], foreground=palette["text"])
    style.configure("Sidebar.TLabel", background=palette["sidebar"], foreground=palette["sidebar_text"])
    style.configure("SidebarBrand.TLabel", background=palette["sidebar"], foreground="#ffffff", font=("Segoe UI", 16, "bold"))
    style.configure("Eyebrow.TLabel", background=palette["card"], foreground=palette["primary"], font=("Segoe UI", 9, "bold"))
    style.configure("Header.TLabel", background=palette["bg"], foreground=palette["text"], font=("Segoe UI", 16, "bold"))
    style.configure("DashboardHeader.TLabel", background=palette["card"], foreground=palette["text"], font=("Segoe UI", 22, "bold"))
    style.configure("DashboardSubtitle.TLabel", background=palette["card"], foreground=palette["muted"], font=("Segoe UI", 10))
    style.configure("RowTitle.TLabel", background=palette["card"], foreground=palette["text"], font=("Segoe UI", 11, "bold"))
    style.configure("RowMeta.TLabel", background=palette["card"], foreground=palette["muted"], font=("Segoe UI", 9))
    style.configure("Footer.TLabel", background=palette["card"], foreground=palette["muted"], font=("Segoe UI", 9))
    style.configure("Section.TLabel", background=palette["bg"], foreground=palette["text"], font=("Segoe UI", 12, "bold"))
    style.configure("CardSection.TLabel", background=palette["card"], foreground=palette["text"], font=("Segoe UI", 12, "bold"))
    style.configure("StatValue.TLabel", background=palette["surface_alt"], foreground=palette["text"], font=("Segoe UI", 18, "bold"))
    style.configure("StatLabel.TLabel", background=palette["surface_alt"], foreground=palette["muted"], font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["muted"])
    style.configure("TLabelframe", background=palette["bg"], bordercolor=palette["border"], relief="groove")
    style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["text"], font=("Segoe UI", 10, "bold"))
    style.configure("TButton", padding=(10, 7), focuscolor=palette["primary"], focusthickness=2)
    style.configure("Compact.TButton", padding=(9, 4))
    style.configure("Secondary.TButton", background=palette["card"], foreground=palette["text"], padding=(11, 7), borderwidth=1)
    style.map("Secondary.TButton", background=[("active", palette["selection"]), ("pressed", palette["border"])])
    style.configure("Update.TButton", background=palette["card"], foreground=palette["muted"], padding=(8, 5), borderwidth=0)
    style.map("Update.TButton", foreground=[("active", palette["accent"])], background=[("active", palette["card"])])
    style.configure("Primary.TButton", background=palette["accent"], foreground=palette["accent_text"], padding=(12, 8), borderwidth=1)
    style.map(
        "Primary.TButton",
        background=[("pressed", palette["accent_active"]), ("active", palette["accent_hover"]), ("disabled", palette["border"])],
        foreground=[("disabled", palette["muted"])],
    )
    style.configure("Nav.TButton", background=palette["sidebar"], foreground=palette["sidebar_text"], padding=(16, 11), borderwidth=0, anchor="w")
    style.map("Nav.TButton", background=[("active", palette["primary"]), ("pressed", palette["primary"])], foreground=[("active", "#ffffff")])
    style.configure("NavPrimary.TButton", background=palette["primary"], foreground="#ffffff", padding=(16, 11), borderwidth=0, anchor="w")
    style.map("NavPrimary.TButton", background=[("active", palette["primary"]), ("pressed", palette["primary"])])
    style.configure("TCheckbutton", background=palette["bg"], foreground=palette["text"])
    style.configure("Card.TCheckbutton", background=palette["card"], foreground=palette["text"])
    style.map("Card.TCheckbutton", background=[("active", palette["card"])])
    style.configure("TRadiobutton", background=palette["bg"], foreground=palette["text"])
    style.configure("TEntry", fieldbackground=palette["card"], foreground=palette["text"], padding=(8, 6))
    style.configure("TCombobox", fieldbackground=palette["card"], background=palette["card"], foreground=palette["text"], padding=(6, 5))
    style.configure("TProgressbar", troughcolor=palette["border"], background=palette["accent"])
    style.configure("Treeview", background=palette["card"], fieldbackground=palette["card"], foreground=palette["text"], bordercolor=palette["border"])
    style.configure("Treeview.Heading", background=palette["bg"], foreground=palette["text"], relief="flat")
    return palette


def style_canvas(widget: tk.Canvas, palette: dict[str, str]) -> None:
    widget.configure(bg=palette["bg"], highlightthickness=0, bd=0)


def style_listbox(widget: tk.Listbox, palette: dict[str, str]) -> None:
    widget.configure(
        bg=palette["card"],
        fg=palette["text"],
        selectbackground=palette["selection"],
        selectforeground=palette["text"],
        highlightthickness=1,
        highlightbackground=palette["border"],
        highlightcolor=palette["accent"],
        relief="flat",
        borderwidth=1,
    )


def style_text(widget: tk.Text, palette: dict[str, str]) -> None:
    widget.configure(
        bg=palette["card"],
        fg=palette["text"],
        insertbackground=palette["text"],
        selectbackground=palette["selection"],
        selectforeground=palette["text"],
        highlightthickness=1,
        highlightbackground=palette["border"],
        highlightcolor=palette["accent"],
        relief="flat",
        borderwidth=1,
    )
