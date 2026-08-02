# Vidio

Vidio is a DreamOS / OE 2.6 Enigma2 plugin for Dreambox One UHD and Dreambox
Two UHD. It keeps the video from the current DVB service, replaces its audio
with a second DVB service, and can delay only the video in 0.1 second steps.

## How it works

Vidio opens the two DVB services through the receiver streaming server. ffmpeg
maps only video from the current service and only audio from the selected
service into a new local MPEG transport stream. The streams are copied without
re-encoding. DreamOS plays that single local stream through its normal decoder
and HDMI audio path.

The old ALSA injection and `selectTrack(-1)` design was removed in 0.2.0. Vidio
now reports Running only after ffmpeg has produced packets and DreamOS has
opened the combined stream.

## Requirements

- Dreambox One UHD or Dreambox Two UHD
- DreamOS / OpenDreambox OE 2.6
- Two correctly configured DVB tuners with access to both satellites
- `/usr/bin/ffmpeg`
- DreamOS streaming server on its standard local port `8001`

The common 5-10 second video delay is timestamp-based and does not require HDD
or USB storage. Very large delays can require substantial player memory.

## Build and install

```sh
make lint
make deb
```

The package is written to `dist/`:

```text
dist/enigma2-plugin-extensions-vidio_0.2.0_arm64.deb
```

Install it and restart Enigma2:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-vidio_0.2.0_arm64.deb
systemctl restart enigma2
```

## Controls

- `OK` on Vidio: toggle On/Off
- `OK` on Audio source: select a DVB service from bouquets or service lists
- `Left` / `Right` on Video delay: adjust by 0.1 seconds
- `Green`: save and apply
- `Red` or `Exit`: close the menu
- Long press `Audio`: open Vidio from live TV

When Vidio is turned Off, or when ffmpeg/local playback fails, the original DVB
service is restored. Runtime diagnostics are written to
`/tmp/vidio-ffmpeg.log`.

## Receiver constraints

DreamOS decides tuner and descrambler allocation. Starting can fail when the
second tuner cannot access the selected satellite, another recording occupies
it, or CI/softcam restrictions prevent two simultaneous decrypted streams.
