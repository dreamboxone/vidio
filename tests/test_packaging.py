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


if __name__ == "__main__":
    unittest.main()
