import unittest

from psk import util


class TestUtil(unittest.TestCase):
    def test_uuid_unique(self):
        self.assertNotEqual(util.new_uuid(), util.new_uuid())

    def test_now_iso_format(self):
        ts = util.now_iso()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        self.assertNotIn("+00:00", ts)

    def test_sha256_known(self):
        self.assertEqual(
            util.sha256_hex(""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(util.sha256_hex("abc"), util.sha256_hex(b"abc"))

    def test_canonical_json_sorted_and_stable(self):
        a = util.canonical_json({"b": 1, "a": 2})
        b = util.canonical_json({"a": 2, "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, '{"a":2,"b":1}')


if __name__ == "__main__":
    unittest.main()
