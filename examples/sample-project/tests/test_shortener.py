import unittest

from shortener import InvalidURL, Shortener, UnknownCode


class ShortenerTest(unittest.TestCase):
    def test_create_then_resolve(self):
        s = Shortener()
        link = s.create("https://example.com/a")
        self.assertEqual(s.resolve(link.code), "https://example.com/a")

    def test_codes_are_unique(self):
        s = Shortener()
        self.assertNotEqual(s.create("https://example.com/a").code, s.create("https://example.com/b").code)

    def test_rejects_non_http_urls(self):
        with self.assertRaises(InvalidURL):
            Shortener().create("ftp://example.com/file")

    def test_unknown_code(self):
        with self.assertRaises(UnknownCode):
            Shortener().resolve("nope")


if __name__ == "__main__":
    unittest.main()
