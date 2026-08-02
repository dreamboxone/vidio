# -*- coding: utf-8 -*-
from __future__ import print_function


DEFAULT_STREAM_PORT = 8001
DEFAULT_OUTPUT_URL = "udp://127.0.0.1:17999?pkt_size=1316"


def is_dvb_service(service_ref):
    return bool(service_ref) and service_ref.startswith("1:")


def service_stream_url(service_ref, port=DEFAULT_STREAM_PORT):
    return "http://127.0.0.1:%d/%s" % (int(port), service_ref)


def build_ffmpeg_args(ffmpeg, video_ref, audio_ref, delay_tenths, output_url=DEFAULT_OUTPUT_URL, stream_port=DEFAULT_STREAM_PORT):
    delay_seconds = max(0, int(delay_tenths)) / 10.0
    args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostdin",
        "-nostats",
        "-progress", "pipe:1",
        "-thread_queue_size", "4096",
        "-analyzeduration", "3000000",
        "-probesize", "5000000",
    ]
    if delay_seconds:
        args.extend(["-itsoffset", "%.1f" % delay_seconds])
    args.extend([
        "-i", service_stream_url(video_ref, stream_port),
        "-thread_queue_size", "4096",
        "-analyzeduration", "3000000",
        "-probesize", "5000000",
        "-i", service_stream_url(audio_ref, stream_port),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "copy",
        "-sn",
        "-dn",
        "-avoid_negative_ts", "make_zero",
        "-max_interleave_delta", "30000000",
        "-muxdelay", "0",
        "-muxpreload", "0",
        "-mpegts_flags", "+resend_headers",
        "-f", "mpegts",
        output_url,
    ])
    return args


def concise_ffmpeg_error(output):
    if not output:
        return "ffmpeg stopped before producing the local stream."
    useful = []
    for raw_line in output.replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line or "=" in line and line.split("=", 1)[0] in (
            "bitrate", "drop_frames", "dup_frames", "fps", "frame", "out_time",
            "out_time_ms", "out_time_us", "progress", "speed", "stream_0_0_q", "total_size",
        ):
            continue
        useful.append(line)
    if not useful:
        return "No packets were received from one or both services."
    return useful[-1][:220]
