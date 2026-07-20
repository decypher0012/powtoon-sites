from __future__ import annotations

import threading
from typing import Callable


class TrayController:
    def __init__(self, show: Callable[[], None], launch_presets: dict[str, Callable[[], None]],
                 check_updates: Callable[[], None], quit_app: Callable[[], None]):
        self.show, self.launch_presets = show, launch_presets
        self.check_updates, self.quit_app = check_updates, quit_app
        self.icon = None

    @staticmethod
    def _image():
        from PIL import Image, ImageDraw
        image = Image.new("RGBA", (64, 64), "#17324d")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 59, 59), radius=12, fill="#246b9e")
        draw.polygon(((23, 16), (50, 32), (23, 48)), fill="white")
        return image

    def start(self) -> None:
        if self.icon is not None:
            return
        import pystray
        preset_items = tuple(pystray.MenuItem(name, lambda _icon, _item, action=action: action())
                             for name, action in self.launch_presets.items())
        menu = pystray.Menu(
            pystray.MenuItem("Open Work Launcher", lambda *_: self.show(), default=True),
            pystray.MenuItem("Launch Preset", pystray.Menu(*preset_items), enabled=bool(preset_items)),
            pystray.MenuItem("Check for Updates", lambda *_: self.check_updates()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda *_: self.quit_app()),
        )
        self.icon = pystray.Icon("WorkLauncher", self._image(), "Work Launcher", menu)
        threading.Thread(target=self.icon.run, name="work-launcher-tray", daemon=True).start()

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
