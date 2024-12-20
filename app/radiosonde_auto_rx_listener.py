from udp_listener import AsyncUDPListener
from settings import Settings
from radiosonde_payload import RadiosondePayload
from utils import Utils
from datetime import datetime, UTC, timedelta
import asyncio
import aiohttp
import logging


logger = logging.getLogger(__name__)


class AsyncRadiosondeAutoRxListener:
    def __init__(self):
        self._settings: Settings = Settings.load_settings()
        self._sondes = {}

        self._purge_interval = 60  # How often to check for old sonde data (in seconds)
        self._purge_task = None  # Task to handle purging of old sonde data

        logger.info("AsyncRadiosondeAutoRxListener initialized.")

    async def start(self):
        logger.info("Starting AsyncRadiosondeAutoRxListener...")
        if self._settings.fetch_from_online:
            logger.info("Fetching data from online sites.")
            await self._listen_web()
        else:
            logger.info("Fetching data from local udp.")
            await self._listen_udp()

    async def _listen_web(self):
        """Uses async requests to fetch data from online sources."""

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        logger.info("Fetching data from online source now..")
        while True:
            logger.info(
                "---------------------------------------\n   [READING DATA FROM ONLINE SOURCE]   \n---------------------------------------"
            )
            url = f"https://s1.radiosondy.info/export/export_map.php?live_map=1&_={int(datetime.now().timestamp() * 1000)}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to fetch data from online source. Status code: {response.status}"
                        )
                        await asyncio.sleep(60)
                        continue
                    data = await response.json()
                    if "features" in data:
                        for feature in data["features"]:
                            if (
                                "geometry" in feature
                                and feature["geometry"]["type"] == "Point"
                            ):
                                coords = (
                                    float(feature["properties"]["latitude"]),
                                    float(feature["properties"]["longitude"]),
                                )
                                if Utils.is_within_range(
                                    self._settings.listener_location.location_tuple,
                                    coords,
                                    self._settings.notification_thresholds.distance_km,
                                ):
                                    if (
                                        float(
                                            feature["properties"]["climbing"].replace(
                                                " m/s", ""
                                            )
                                        )
                                        < 1
                                    ):
                                        if (
                                            int(
                                                feature["properties"][
                                                    "altitude"
                                                ].replace(" m", "")
                                            )
                                            < self._settings.notification_thresholds.altitude_meters
                                        ):
                                            logger.info(
                                                f"Radiosonde detected within range and below altitude threshold."
                                            )
                                            if (
                                                self._sondes.get(
                                                    feature["properties"]["id"]
                                                )
                                                is None
                                            ):
                                                self._sondes[
                                                    feature["properties"]["id"]
                                                ] = {
                                                    "notify": True,
                                                    "landing_notify": False,
                                                    "altitude": int(
                                                        feature["properties"][
                                                            "altitude"
                                                        ].replace(" m", "")
                                                    ),
                                                    "last_update": datetime.now(UTC),
                                                    "data": Utils.map_json_to_radiosonde_payload(
                                                        feature
                                                    ),
                                                }
                                                logger.info(
                                                    f"New radiosonde detected: {feature['properties']['id']}. Sending notification."
                                                )

                                                await Utils.send_threshold_notification(
                                                    Utils.map_json_to_radiosonde_payload(
                                                        feature
                                                    )
                                                )

            self._purge_task = asyncio.create_task(self.purge_old_sondes())
            logger.info("---------------------------------------")
            await asyncio.sleep(60)

    async def _listen_udp(self):
        # Instantiate the UDP listener.
        udp_listener = AsyncUDPListener(
            callback=self.handle_payload_summary,
            port=self._settings.udp_broadcast.listen_port,
        )

        # Start the UDP listener
        listener_task = asyncio.create_task(udp_listener.listen())

        # Start the purge task to remove old sonde data
        self._purge_task = asyncio.create_task(self.purge_old_sondes())

        # From here, everything happens in the callback function above.
        try:
            await listener_task
        # Catch CTRL+C nicely.
        except Exception as e:
            logger.exception(e)
        finally:
            # Close UDP listener.
            udp_listener.stop()
            await self.stop_purge_task()

    async def handle_payload_summary(self, packet: dict):
        """Handle a 'Payload Summary' UDP broadcast message, supplied as a dict."""
        model = RadiosondePayload(**packet)

        current_time = datetime.now(UTC)
        range_km = self._settings.notification_thresholds.distance_km
        home = self._settings.listener_location.location_tuple

        if self._sondes.get(model.callsign) is None:
            self._sondes[model.callsign] = {
                "notify": False,
                "landing_notify": False,
                "altitude": 0,
                "last_update": current_time,
                "data": model,
            }
            logger.info(f"New radiosonde detected: {model.callsign}.")

        if (
            self._is_descending(model)
            and self._is_below_threshold(model)
            and Utils.is_within_range(home, model.location_tuple, range_km)
            and not self._sondes[model.callsign]["notify"]
        ):  # sonde is falling
            logger.debug(
                f"Radiosonde {model.callsign} is descending, within range, and below altitude threshold. Sending notification."
            )
            await Utils.send_threshold_notification(model)
            self._sondes[model.callsign]["notify"] = True

        elif (
            not self._is_descending(model)
            or not self._is_below_threshold(model)
            or not Utils.is_within_range(home, model.location_tuple, range_km)
        ):
            if self._sondes[model.callsign]["notify"]:
                # Reset notify flag if conditions are not met
                logger.info(
                    f"Conditions not met for radiosonde {model.callsign}. Resetting notification flag."
                )
                self._sondes[model.callsign]["notify"] = False

        self._sondes[model.callsign]["altitude"] = model.altitude
        self._sondes[model.callsign]["last_update"] = current_time
        self._sondes[model.callsign]["data"] = model

    def _is_descending(self, model: RadiosondePayload):
        return model.altitude < self._sondes[model.callsign]["altitude"]

    def _is_below_threshold(self, model: RadiosondePayload):
        return model.altitude < self._settings.notification_thresholds.altitude_meters

    async def purge_old_sondes(self):
        """Periodically check and purge sonde data older than 2 hours."""
        range_km = self._settings.notification_thresholds.distance_km
        home = self._settings.listener_location.location_tuple

        while True:
            logger.info("Purging old radiosonde data...")
            current_time = datetime.now(UTC)

            for callsign, sonde_data in self._sondes.items():
                last_updated = sonde_data.get("last_update")
                landing_notify = sonde_data.get("landing_notify")
                model = sonde_data.get("data")
                timeout = (
                    self._settings.notification_thresholds.landing_point_timeout_minutes
                )

                if (
                    last_updated
                    and timeout > 0
                    and (current_time - last_updated) > timedelta(minutes=timeout)
                    and not landing_notify
                    and self._is_below_threshold(model)
                    and Utils.is_within_range(home, model.location_tuple, range_km)
                ):
                    await Utils.send_landing_notification(model)
                    sonde_data["landing_notify"] = True

                if last_updated and (current_time - last_updated) > timedelta(hours=2):
                    del self._sondes[callsign]
                    logger.info(
                        f"Purged radiosonde data for {callsign} (older than 2 hours)."
                    )

            await asyncio.sleep(self._purge_interval)  # Wait for the next purge cycle

    async def stop_purge_task(self):
        """Stop the purge task gracefully."""
        if self._purge_task:
            logger.info("Stopping purge task.")
            self._purge_task.cancel()  # Gracefully stop the purge task
            try:
                await self._purge_task
            except asyncio.CancelledError:
                logger.info("Purge task cancelled.")
