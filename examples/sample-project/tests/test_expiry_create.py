"""Slice 01: links can carry an optional expiry. Planned in .ai/slices/01/TEST_PLAN.md."""

import unittest

from shortener import InvalidTTL, Link, Shortener
from shortener.service import MAX_TTL_SECONDS


class FixedClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class CreateWithExpiryTest(unittest.TestCase):
    def test_ac1_ttl_sets_expires_at_in_utc_seconds(self):
        s = Shortener(clock=FixedClock(1_000.0))
        self.assertEqual(s.create("https://example.com", ttl_seconds=60).expires_at, 1_060.0)

    def test_ac2_no_ttl_means_never_expires(self):
        self.assertIsNone(Shortener().create("https://example.com").expires_at)

    def test_ac3_rejects_zero_negative_and_too_long(self):
        s = Shortener()
        for bad in (0, -1, MAX_TTL_SECONDS + 1):
            with self.subTest(ttl=bad), self.assertRaises(InvalidTTL):
                s.create("https://example.com", ttl_seconds=bad)

    def test_ac3_rejects_non_integer_ttl(self):
        s = Shortener()
        for bad in (1.5, "60", True):
            with self.subTest(ttl=bad), self.assertRaises(InvalidTTL):
                s.create("https://example.com", ttl_seconds=bad)

    def test_ac3_accepts_the_boundaries(self):
        s = Shortener(clock=FixedClock(0.0))
        self.assertEqual(s.create("https://example.com", ttl_seconds=1).expires_at, 1.0)
        self.assertEqual(s.create("https://example.com", ttl_seconds=MAX_TTL_SECONDS).expires_at,
                         float(MAX_TTL_SECONDS))

    def test_ac4_existing_positional_construction_still_works(self):
        link = Link("abc", "https://example.com", 5.0)
        self.assertIsNone(link.expires_at)

    def test_ac4_resolve_unchanged_for_links_with_expiry(self):
        s = Shortener(clock=FixedClock(0.0))
        link = s.create("https://example.com", ttl_seconds=10)
        self.assertEqual(s.resolve(link.code), "https://example.com")


if __name__ == "__main__":
    unittest.main()
