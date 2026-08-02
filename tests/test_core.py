import importlib.util
import pathlib
import unittest


CORE = pathlib.Path(__file__).parents[1] / "usr/lib/enigma2/python/Plugins/Extensions/Vidio/core.py"
SPEC = importlib.util.spec_from_file_location("vidio_core", CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class CoreTests(unittest.TestCase):
    def test_builds_lossless_two_input_remux(self):
        args = core.build_ffmpeg_args("/usr/bin/ffmpeg", "1:video:", "1:audio:", 50)
        self.assertEqual(args.count("-i"), 2)
        self.assertIn("0:v:0", args)
        self.assertIn("1:a:0", args)
        self.assertIn("copy", args)
        self.assertIn("5.0", args)
        self.assertNotIn("alsa", args)

    def test_zero_delay_omits_timestamp_offset(self):
        args = core.build_ffmpeg_args("ffmpeg", "1:video:", "1:audio:", 0)
        self.assertNotIn("-itsoffset", args)

    def test_only_dvb_references_are_accepted(self):
        self.assertTrue(core.is_dvb_service("1:0:1:1234:"))
        self.assertFalse(core.is_dvb_service("4097:0:1:http%3a//example"))

    def test_error_summary_ignores_progress_lines(self):
        output = "out_time_ms=10\nprogress=continue\nServer returned 503 Service Unavailable\n"
        self.assertEqual(core.concise_ffmpeg_error(output), "Server returned 503 Service Unavailable")


if __name__ == "__main__":
    unittest.main()
