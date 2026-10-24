# UniFi EAV Bridge for Home Assistant

Control UniFi Enterprise AV (EAV) Bridge routing from Home Assistant: pick which
source feeds a display group, turn streams on and off, and see a live preview of
each source's HDMI input.

Built on the **undocumented** `proav` API the UniFi Network AV Manager uses.
Firmware updates can change it.

## Entities

For every AV group in AV Manager (Ports → AV Manager):

| Entity | What it does |
|---|---|
| `select.<group>_video_source` | Which source bridge feeds the group's displays. Options are every bridge that can act as a source. |
| `switch.<group>_video_stream` | Enables or disables the group (stops or starts the stream). |

For every source bridge: `camera.<bridge>_input_preview`, a still of its HDMI input.

Audio groups get the same `select` and `switch` entities. New groups created in
AV Manager show up automatically within 30 seconds.

## Install

1. Copy `custom_components/unifi_eav` into your Home Assistant `/config/custom_components/`
   or in HACS: ⋮ → Custom repositories → `https://github.com/atramiel/ha-unifi-eav`, type Integration, then install **UniFi EAV Bridge**.
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **UniFi EAV Bridge**.
4. Enter the console address (e.g. `192.168.0.1`) and a **local** UniFi user.
   Create one in UniFi OS → Admins & Users with the Network app's Site Admin role.
   Don't use your Ubiquiti cloud account; 2FA isn't supported.

## API reference

All under `https://<console>/proxy/network/v2/api/site/<site>/`:

| Method | Path | Notes |
|---|---|---|
| GET | `proav/video/matrix`, `proav/audio/matrix` | Bridges, hosts (sources), clients (displays), groups |
| POST | `proav/{video,audio}/group` | Create group |
| PUT | `proav/{video,audio}/group/{id}` | Replace group (send the whole object) |
| DELETE | `proav/{video,audio}/group/{id}` | Delete group |
| GET | `proav/snapshot/{mac}` | JPEG of a source's input |
| POST | `proav/video/set-tv-wall-calibration`, `unset-tv-wall-calibration` | TV wall |

Auth: `POST /api/auth/login` with `{username, password, rememberMe}` sets a
session cookie and returns `x-csrf-token`; send that header on every request.

A group looks like:

```json
{
  "id": "6adc3fd9dfe874c1199f0f9e", "name": "Garage", "type": "VIDEO",
  "enabled": true, "channel": 2,
  "host":    {"mac": "<source mac>", "enabled": true, "refresh_rate": "AUTO", "host_type": "VIDEO"},
  "clients": [{"mac": "<display mac>", "enabled": true, "mode": "UNICAST",
               "resolution": "AUTO", "audio_enabled": true, "audio_mode": "PCM",
               "color_format": "RGB", "client_type": "VIDEO"}]
}
```

## Limitations

- Switching a group's source moves **every display in that group** to the new source.
  To route displays independently, give each its own group in AV Manager.
- A source that already feeds another group may be rejected by the console; the
  error shows in Home Assistant.
- Group create/delete and TV wall calibration aren't exposed as entities yet.

## Tests

`pip install pytest-homeassistant-custom-component PyTurboJPEG && pytest tests`

## License

MIT
