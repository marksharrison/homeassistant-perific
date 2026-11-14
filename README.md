# Perific Meter for Home Assistant

Cloud-polling integration for Perific phase meters on `https://api.enegic.com`.
It polls every 30 seconds and creates one device for each Phase meter on the
account, including meters shared with that account.

Each device exposes:

| Sensor | Unit | Source |
| --- | --- | --- |
| Voltage L1–L3 | V | Realtime packet |
| Current L1–L3 | A | Realtime packet |
| Apparent power L1–L3 | VA | Realtime voltage × current |
| Total apparent power | VA | Sum of the phases that have both voltage and current |
| Total imported energy | kWh | Minute packet (`hwi`) |
| Total exported energy | kWh | Minute packet (`hwo`) |

Current is positive while the meter is importing and negative while it is exporting.
Apparent power is `|current| × voltage`. These packets do not include a measured
watt value. The energy sensors are lifetime totals (`total_increasing`).

## Installation

### HACS

Add `Pokeyo-AB/homeassistant-perific` as a custom repository with the category
**Integration**. Install **Perific Meter**, then restart Home Assistant.

### Manual

Copy `custom_components/perific` to `/config/custom_components/perific`, then
restart Home Assistant. The domain directory must be named `perific`.

Restart from **Settings > System > Restart**, or run `ha core restart`.

## Configuration

The integration is configured only through the UI.

1. Go to **Settings > Devices & services > Add integration**.
2. Search for **Perific Meter**.
3. Enter the Perific account username and password.

One config entry is created per account. Setup checks the credentials against
the API before the entry is saved. An expired API token is refreshed once with
the stored password. If that login is rejected, Home Assistant starts a reauth
flow that asks for the password only.

Diagnostics redact the username, password, and MAC address.

## Energy Dashboard

Use **Total imported energy** and **Total exported energy** from the device
page. Entity IDs are based on the meter name Home Assistant assigns, so pick
them from the device instead of copying a fixed id.

An optional utility meter can track cycles of the imported-energy sensor:

```yaml
utility_meter:
  monthly_energy:
    source: sensor.REPLACE_WITH_IMPORTED_ENERGY_ENTITY
    cycle: monthly
  daily_energy:
    source: sensor.REPLACE_WITH_IMPORTED_ENERGY_ENTITY
    cycle: daily
```
