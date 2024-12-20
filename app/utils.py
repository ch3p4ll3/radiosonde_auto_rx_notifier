import apprise
from geopy import distance
import asyncio

from radiosonde_payload import RadiosondePayload
from settings import Settings


class Utils:
    @staticmethod
    def get_distance(base_coordinates, sonde_coordinates):
        return distance.distance(base_coordinates, sonde_coordinates).km

    @staticmethod
    def is_within_range(base_coordinates, sonde_coordinates, range_km):
        distance = Utils.get_distance(base_coordinates, sonde_coordinates)
        return distance <= range_km

    @staticmethod
    async def send_notification(message_body, title):
        settings = Settings.load_settings()

        apobj = apprise.Apprise()

        for service in settings.notifications.services:
            if service.enabled:
                apobj.add(service.url)

        # notify all of the services loaded into our Apprise object.
        await apobj.async_notify(body=message_body, title=title)

    @staticmethod
    async def map_json_to_radiosonde_payload(json_payload: dict):
        """Mapp
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [1.1515, 43.0685, 8021]}, 'properties': {'id': 'MEA901464', 'type': 'M20', 'startplace': 'Aire Sur Adour\t(FR)', 'frequency': '404.00 MHz', 'report': '2024-12-20 10:34:54z', 'speed': '78 km/h', 'course': '158 °', 'climbing': '-10.0 m/s', 'altitude': '8021 m', 'latitude': '43.0685', 'longitude': '1.1515', 'icon': 'sondeIcon'}}
        to a RadiosondePayload object
        """
        return RadiosondePayload(
            callsign=json_payload["properties"]["id"],
            model=json_payload["properties"]["type"],
            freq=float(json_payload["properties"]["frequency"].replace(" MHz", "")),
            batt=-1,
            vel_v=float(json_payload["properties"]["climbing"].replace(" m/s", "")),
            vel_h=float(json_payload["properties"]["speed"].replace(" km/h", "")),
            altitude=int(json_payload["properties"]["altitude"].replace(" m", "")),
            latitude=float(json_payload["properties"]["latitude"]),
            longitude=float(json_payload["properties"]["longitude"]),
        )

    @staticmethod
    async def send_landing_notification(packet: RadiosondePayload):
        settings = Settings.load_settings()

        message_body = f"""
The radiosonde is nearing its landing site! Based on the latest telemetry data, here is a detailed update:

📍 Landing Prediction:
📍 **Landing Prediction**:
- **Location**: {packet.latitude}, {packet.longitude}
- **Last Known Altitude**: {packet.altitude} meters
- **Distance from Listener**: {round(Utils.get_distance(settings.listener_location.location_tuple, packet.location_tuple), 2)} km

📊 **Radiosonde Details**:
- **Callsign**: {packet.callsign}
- **Model**: {packet.model}
- **Frequency**: {packet.freq}
- **Battery**: {packet.batt} V
- **Last Known Speed**: {packet.vel_v} m/s



Click the link to view the location on Google Maps: [Google Maps](https://www.google.com/maps?q={packet.latitude},{packet.longitude})

💡 Recommendation:
If you're planning retrieval, ensure you have the necessary equipment and safety precautions. The area might be remote or challenging to access.
"""

        await Utils.send_notification(message_body, "🚨 Radiosonde Alert 🚨")

    @staticmethod
    async def send_threshold_notification(packet: RadiosondePayload):
        settings = Settings.load_settings()

        message_body = f"""
The radiosonde is within {settings.notification_thresholds.distance_km} km and below {settings.notification_thresholds.altitude_meters} meters altitude.

📍 **Landing Prediction**:
- **Location**: {packet.latitude}, {packet.longitude}
- **Last Known Altitude**: {packet.altitude} meters
- **Distance from Listener**: {round(Utils.get_distance(settings.listener_location.location_tuple, packet.location_tuple), 2)} km

📊 **Radiosonde Details**:
- **Callsign**: {packet.callsign}
- **Model**: {packet.model}
- **Frequency**: {packet.freq}
- **Battery**: {packet.batt} V
- **Last Known Speed**: {packet.vel_v} m/s

Click the link to view the location on Google Maps: [Google Maps](https://www.google.com/maps?q={packet.latitude},{packet.longitude})
"""

        await Utils.send_notification(message_body, "🚨 Radiosonde Alert 🚨")
