from __future__ import annotations

import random

# Gacha pools, drop tables and befriend rolls decide what a player receives, so
# they use the OS entropy source instead of the seeded Mersenne Twister that
# `random` uses by default and whose stream can be reconstructed from output.
rng = random.SystemRandom()
