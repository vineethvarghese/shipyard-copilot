> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: none.
# Glossary: link-expiry

### Link
A short code mapped to a URL, with an optional expiry chosen at creation.
Avoid: alias, redirect
Source: src/shortener/models.py:8

### TTL
Time to live: whole seconds from creation until the link expires. Chosen once, at creation.
Avoid: lifetime, duration
Source: the human's words at P4 round 1 ("a TTL in seconds, set when the link is made")

### Expired
A link whose `expires_at` is at or before the clock. An expired link stays in the store.
Avoid: dead, deleted
Source: the human's words at P4 round 1 (G2: "keep them, don't delete them")
