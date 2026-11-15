# Calm Home Assistant Integration

Play today's Daily Calm on Home Assistant media players using
[python-calm-client](https://github.com/dcode/python-calm-client).

Requires Home Assistant 2026.10.4 or newer and a Calm account with access to the
session. This unofficial integration uses Calm's undocumented web API.

## Installation

Copy `custom_components/calm/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Open **Settings → Devices & Services → Add Integration**, search for **Calm**,
and enter your Calm email address and password. Sign-in uses Calm's email and
password authentication; social sign-in is not supported.

In an automation's **Play Media** action, select your speaker and choose
**Calm → Daily Calm** in the media browser. The saved media identifier
`media-source://calm/daily` resolves the current session each time it is played.

The speaker must be able to fetch Calm's audio URL directly. Live account
authentication and speaker playback have not yet been verified.

## Development

Install the
[shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks),
then run the checks from the repository root:

```sh
mise run check
```

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
