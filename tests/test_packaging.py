import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


def control_value(path, key):
    prefix = key + ":"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise AssertionError("Missing %s in %s" % (key, path))


class PackagingTests(unittest.TestCase):
    def test_package_versions_match_plugin(self):
        namespace = {}
        init_path = ROOT / "usr/lib/enigma2/python/Plugins/Extensions/Vidio/__init__.py"
        exec(init_path.read_text(encoding="utf-8"), namespace)
        version = namespace["PLUGIN_VERSION"]
        self.assertEqual(control_value(ROOT / "DEBIAN/control", "Version"), version)
        self.assertEqual(control_value(ROOT / "IPK/control", "Version"), version)

    def test_ipk_is_architecture_independent(self):
        self.assertEqual(control_value(ROOT / "IPK/control", "Architecture"), "all")

    def test_upgrade_scripts_remove_stale_bytecode(self):
        for package_dir in ("DEBIAN", "IPK"):
            preinst = (ROOT / package_dir / "preinst").read_text(encoding="utf-8")
            self.assertIn("Plugins/Extensions/Vidio", preinst)
            self.assertIn("*.pyc", preinst)
            self.assertIn("__pycache__", preinst)
        ipk_builder = (ROOT / "build-ipk.sh").read_text(encoding="utf-8")
        self.assertIn('IPK/preinst', ipk_builder)

    def test_restart_falls_back_to_init_script(self):
        for package_dir in ("DEBIAN", "IPK"):
            postinst = (ROOT / package_dir / "postinst").read_text(encoding="utf-8")
            self.assertIn("systemctl try-restart enigma2", postinst)
            self.assertIn("/etc/init.d/enigma2 restart", postinst)

    def test_optional_enigma_events_are_feature_detected(self):
        plugin = (ROOT / "usr/lib/enigma2/python/Plugins/Extensions/Vidio/plugin.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('getattr(iPlayableService, "evVideoPtsValid", None)', plugin)
        self.assertNotIn("event == iPlayableService.evVideoPtsValid", plugin)


if __name__ == "__main__":
    unittest.main()
