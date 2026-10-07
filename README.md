# Vidio

Vidio is an Enigma2 plugin for DreamOS, OpenATV, OpenPLi, and compatible images.
It keeps the video from the current DVB service, replaces its audio with a
second DVB service, and can delay only the video in 0.1 second steps.

## How it works

Vidio opens the two DVB services through the receiver streaming server. ffmpeg
maps only video from the current service and only audio from the selected
service into a new local MPEG transport stream. The streams are copied without
re-encoding. DreamOS plays that single local stream through its normal decoder
and HDMI audio path.

The old ALSA injection and `selectTrack(-1)` design was removed in 0.2.0. Vidio
now reports Running only after ffmpeg has produced packets and DreamOS has
opened the combined stream.

## Targets

- Dreambox One/Two UHD on DreamOS: ARM64 `.deb`
- ARM 32-bit Enigma2 receivers: architecture-independent `.ipk`
- MIPS Enigma2 receivers: architecture-independent `.ipk`
- Two correctly configured DVB tuners with access to both satellites
- `/usr/bin/ffmpeg`
- Enigma2 streaming server on its standard local port `8001`
- IPTV playback service type `4097`

The common 5-10 second video delay is timestamp-based and does not require HDD
or USB storage. Very large delays can require substantial player memory.

## Build and install

```sh
make lint
make packages
```

Both packages are written to `dist/`:

```text
dist/enigma2-plugin-extensions-vidio_0.2.3_arm64.deb
dist/enigma2-plugin-extensions-vidio_0.2.3_all.ipk
```

Install the DreamOS package:

```sh
dpkg -i /tmp/enigma2-plugin-extensions-vidio_0.2.3_arm64.deb
systemctl restart enigma2
```

Install the ARM32/MIPS package:

```sh
opkg install /tmp/enigma2-plugin-extensions-vidio_0.2.3_all.ipk
```

`Architecture: all` is intentional: Vidio contains Python and image assets but
no compiled CPU-specific executable. The receiver feed supplies the correct
ARM32 or MIPS build of ffmpeg.

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

Enigma2 decides tuner and descrambler allocation. Starting can fail when the
second tuner cannot access the selected satellite, another recording occupies
it, or CI/softcam restrictions prevent two simultaneous decrypted streams.

---

## 💚 Support this project

If this project has been useful to you, you can support it with Tether:

**USDT — BEP20 (BSC) network only**

```
0x56daaa6b76d88ee0c8dba8042121f4b77de0a813
```

> [!WARNING]
> This address is for USDT on the BEP20 (BSC) network only. Any other coin, or USDT sent over any other network, is lost.
