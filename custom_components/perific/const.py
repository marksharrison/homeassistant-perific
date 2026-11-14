"""Constants for the Perific Meter integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "perific"
API_URL: Final = "https://api.enegic.com"
PLATFORMS: Final = (Platform.SENSOR,)
UPDATE_INTERVAL_SECONDS: Final = 30
