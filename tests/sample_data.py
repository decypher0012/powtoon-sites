from work_launcher.config import WebsiteConfig, default_config


def populated_config():
    config = default_config()
    config.websites = [
        WebsiteConfig("Admin", "https://admin.example.test", browser_profile="chrome-work"),
        WebsiteConfig("Gmail", "https://mail.google.com/", browser_profile="chrome-work"),
        WebsiteConfig("Calendar", "https://calendar.google.com/", browser_profile="chrome-work"),
        WebsiteConfig("Keep", "https://keep.google.com/", browser_profile="chrome-work"),
        WebsiteConfig("Dashboard", "https://dashboard.example.test", browser_profile="chrome-work"),
        WebsiteConfig("Identity", "https://identity.example.test", browser_profile="chrome-work"),
    ]
    return config
