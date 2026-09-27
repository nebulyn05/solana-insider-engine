from __future__ import annotations

import re

_BASE58 = r"[1-9A-HJ-NP-Za-km-z]"
_SOLANA_ADDRESS = re.compile(rf"(?<!{_BASE58})({_BASE58}{{32,44}})(?!{_BASE58})")


def extract_solana_mints(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in _SOLANA_ADDRESS.finditer(text):
        value = match.group(1)
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
