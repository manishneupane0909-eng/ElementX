import re
from typing import Any, Optional

from services.llm_client import chat_completion, parse_json_from_llm


def _regex_parse_synthesis(notes: str) -> dict[str, Any]:
    text = notes.strip()
    lower = text.lower()
    result: dict[str, Any] = {
        "method": "arc_melt",
        "anneal_temp_c": None,
        "anneal_time_h": None,
        "notes": text[:500] if text else None,
    }

    if "induction" in lower:
        result["method"] = "induction_melt"
    elif "ball mill" in lower or "ball-mill" in lower:
        result["method"] = "ball_mill"
    elif "arc" in lower:
        result["method"] = "arc_melt"
    elif "melt" in lower:
        result["method"] = "other"

    temp_match = re.search(
        r"(?:anneal(?:ed|ing)?|heat(?:ed|ing)?|temp(?:erature)?)[^\d]{0,20}(\d{3,4})\s*°?\s*c",
        lower,
    )
    if not temp_match:
        temp_match = re.search(r"(\d{3,4})\s*°?\s*c", lower)
    if temp_match:
        result["anneal_temp_c"] = float(temp_match.group(1))

    time_match = re.search(r"(\d+(?:\.\d+)?)\s*h(?:ours?|r)?", lower)
    if time_match:
        result["anneal_time_h"] = float(time_match.group(1))

    dopants = []
    for el in ["C", "B", "Ga", "In", "Si", "Cu"]:
        pct = re.search(rf"{el.lower()}[^\d]{{0,10}}(\d+(?:\.\d+)?)\s*%", lower)
        if pct:
            dopants.append({"element": el if el != "C" else "C", "fraction": float(pct.group(1)) / 100.0})
    if dopants:
        result["dopants"] = dopants

    return result


async def parse_synthesis_notes(notes: str) -> dict[str, Any]:
    system = (
        "Extract synthesis parameters from lab notes. Return ONLY valid JSON with keys: "
        'method (one of arc_melt, induction_melt, ball_mill, other), '
        "anneal_temp_c (number or null), anneal_time_h (number or null), "
        "notes (short summary string), dopants (array of {element, fraction} where fraction is 0-1)."
    )
    user = f"Lab notes:\n\n{notes}"

    content, source = await chat_completion(system, user, max_tokens=800)
    parsed = parse_json_from_llm(content)

    if parsed and isinstance(parsed, dict):
        method = parsed.get("method", "arc_melt")
        if method not in ("arc_melt", "induction_melt", "ball_mill", "other"):
            method = "other"
        return {
            "synthesis": {
                "method": method,
                "anneal_temp_c": parsed.get("anneal_temp_c"),
                "anneal_time_h": parsed.get("anneal_time_h"),
                "notes": parsed.get("notes") or notes[:500],
            },
            "dopants": parsed.get("dopants") or [],
            "source": source,
        }

    heuristic = _regex_parse_synthesis(notes)
    dopants = heuristic.pop("dopants", [])
    return {
        "synthesis": heuristic,
        "dopants": dopants,
        "source": "regex" if source == "heuristic" else source,
    }
