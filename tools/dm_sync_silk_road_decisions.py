#!/usr/bin/env python3
"""Register the Silk Road market decision as an inert compatibility shell."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "common/decisions/dlc_decisions/tgp/tgp_silk_road_decisions.txt"
)


def main() -> None:
    text = """# Temporarily disabled for the Spring-Autumn total-conversion map.
# The stable decision key is retained for script compatibility.

visit_silk_road_market_decision = {
\tpicture = {
\t\treference = "gfx/interface/illustrations/decisions/tgp_silk_road.dds"
\t}
\tdesc = visit_silk_road_market_decision_desc
\tselection_tooltip = visit_silk_road_market_decision_tooltip
\tai_check_interval = 0
\tis_shown = { always = no }
\tis_valid = { always = no }
\tis_valid_showing_failures_only = { always = no }
\teffect = { }
\tai_potential = { always = no }
\tai_will_do = { value = 0 }
}
"""
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8-sig", newline="\n")
    print(f"Wrote inert Silk Road market decision to {TARGET}")


if __name__ == "__main__":
    main()
