# Vidio

Vidio is an experimental DreamOS / OE 2.6 Enigma2 plugin for Dreambox One UHD
and Dreambox Two UHD receivers.

It lets you watch the current video service while replacing its audio with the
audio from a second service. The sync control only delays the current video by
using Enigma2 timeshift. It does not delay or process the replacement audio.
This is intended for cases where the Persian audio feed arrives several seconds
later than the clean sports video feed.

## Target

- Dreambox One UHD / Dreambox Two UHD
- DreamOS / OpenDreambox OE 2.6
- Two usable tuners
- `ffmpeg` installed at `/usr/bin/ffmpeg`
- WebInterface enabled on `127.0.0.1:80`
- Timeshift configured with writable HDD/USB storage at `/media/hdd` or `/media/usb`

## Install

Build the Dreambox `.deb` package on Linux, WSL, or GitHub Actions:

```sh
make deb
```

The package will be written to `dist/`, for example:

```text
dist/enigma2-plugin-extensions-vidio_0.1.0_arm64.deb
```

Install it on the receiver:

```sh
scp dist/enigma2-plugin-extensions-vidio_0.1.0_arm64.deb root@dreambox:/tmp/
ssh root@dreambox "dpkg -i /tmp/enigma2-plugin-extensions-vidio_0.1.0_arm64.deb || apt-get -f install"
```

For manual testing, copy the plugin directory to the receiver:

```sh
scp -r usr/lib/enigma2/python/Plugins/Extensions/Vidio root@dreambox:/usr/lib/enigma2/python/Plugins/Extensions/
```

Restart Enigma2:

```sh
systemctl restart enigma2
```

Open Vidio from the Plugins menu. It is inactive by default and does not hook
the Audio key.

## Controls

- `OK`: choose audio service / toggle selected item
- `Left` / `Right`: change video delay by 0.1 seconds
- `Green`: save current settings and start
- `Red`: stop Vidio
- `Exit`: close

## Notes

The first version intentionally uses the receiver's local stream URL with
`ffmpeg` for the second-service audio:

```text
http://127.0.0.1/web/stream.m3u?ref=<service-reference>
```

This keeps audio service acquisition separate from the currently watched video
service. Tuner availability is still checked and shown in the UI, but exact
front-end allocation is ultimately decided by DreamOS.

Positive audio delay is deliberately not implemented. If `Video delay` is set
to `5.0`, Vidio buffers the current video for about five seconds and then plays
the selected second-service audio live.
