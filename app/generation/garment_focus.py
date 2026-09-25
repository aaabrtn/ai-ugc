"""Shared "which garment is this video promoting" vocabulary.

Lives in its own leaf module (not template.py or vision.py) so both can
import it without a circular import -- template.py already imports from
vision.py, so vision.py importing back from template.py would create a cycle.

Keys are the only valid `Product.garment_type` values, besides "" for
unspecified (the default -- existing products, and anyone who skips this
field, get exactly today's behaviour with no focus language at all).

Shoes is deliberately not included: the SOP's hard "ankles and feet never
shown" rule (Section 8) makes a shoes-focused video incompatible with this
video format entirely -- it would need a genuinely different template (an
actual view of her feet), not just different choreography within this one.
"""

GARMENT_TYPE_LABELS = {
    "trousers": "trousers",
    "shorts": "shorts",
    "dress": "dress",
    "top": "top",
    "jacket": "jacket",
}

# Correct English possessive per type. Deliberately hardcoded, not derived by
# a lexical rule like "ends with s => plural, drop the s" -- that misfires on
# "dress", which ends in "s" as part of its spelling but is singular
# ("dress's", not "dress'"). Fine to hardcode since the type set is small
# and fixed.
GARMENT_TYPE_POSSESSIVES = {
    "trousers": "trousers'",
    "shorts": "shorts'",
    "dress": "dress's",
    "top": "top's",
    "jacket": "jacket's",
}
