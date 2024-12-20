from pydantic import BaseModel, PositiveFloat


class NotificationThresholds(BaseModel):
    distance_km: PositiveFloat  # Distance threshold in kilometers (e.g., send notification if radiosonde is within 20km)
    altitude_meters: float  # Altitude threshold in meters (e.g., send notification if altitude is below 10,000 meters)
    landing_point_timeout_minutes: int = (
        5  # Specifies the duration (in minutes) of inactivity after which the landing point is sent. 0 = Disabled
    )
