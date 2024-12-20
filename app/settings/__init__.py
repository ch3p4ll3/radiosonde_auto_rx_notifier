from pathlib import Path

from pydantic import BaseModel, Field
from yaml import safe_load, dump

from .listener_location import ListenerLocation
from .notification_thresholds import NotificationThresholds
from .udp_broadcast import UDPBroadcast
from .notifications import Notifications


class Settings(BaseModel):
    listener_location: ListenerLocation
    notification_thresholds: NotificationThresholds
    udp_broadcast: UDPBroadcast
    fetch_from_online: bool = Field(default=True)
    notifications: Notifications

    @classmethod
    def load_settings(cls):
        settings_file_path = Path(__file__).parent.parent.parent / "data/config.yml"

        if not settings_file_path.exists():
            settings = cls.get_default_settings()

            with open(settings_file_path, "w") as settings_file:
                dump(settings.model_dump(mode="json"), settings_file, indent=2)

            return settings

        with open(settings_file_path, "r") as settings_file:
            return cls(**safe_load(settings_file))

    @classmethod
    def get_default_settings(cls):
        data = {
            "listener_location": {"latitude": 0, "longitude": 0, "altitude": 0},
            "notification_thresholds": {"distance_km": 20, "altitude_meters": 1000},
            "udp_broadcast": {"enabled": True, "listen_port": 55673},
            "fetch_from_online": True,
            "notifications": {"services": [{"url": "", "enabled": True}]},
        }

        return cls(**data)
