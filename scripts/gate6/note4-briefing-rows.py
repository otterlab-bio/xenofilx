#!/usr/bin/env python3
"""Emit job-summary rows for a Note 4 per-cell comparison report.

The Note 4 briefings exist to report measured recall against the recorded values, but the
comparison report nests those numbers under ``comparisons[].metrics.<name>``. A one-line
``summary-field.sh`` lookup cannot reach them: that helper resolves scalars by dotted path, so a
list element resolves to ``-`` and the briefing would report counts instead of results.

This script prints one ``assertion|expected|observed|result`` line per evaluated cell, which is
exactly the ``--check`` argument format ``job-summary.sh`` consumes. Keeping the formatting in a
script rather than in a workflow ``run:`` block keeps it testable outside CI and avoids the
block-scalar indentation hazard that has broken these workflows before.

usage:
  note4-briefing-rows.py --report ci-artifacts/gradient-comparison.json
  note4-briefing-rows.py --report ci-artifacts/grid-comparison.json \\
      --metrics modern_recall legacy_recall modern_spec legacy_spec

A missing report, an unreadable report, or a report with no comparisons prints nothing and exits
0, so a job that died before producing evidence still renders the rest of its briefing.
"""

from __future__ import annotations

import argparse
import json
import pathlib

DEFAULT_METRICS = ("modern_recall", "legacy_recall")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=list(DEFAULT_METRICS),
        help="Metric names to show per cell, in order (default: modern_recall legacy_recall)",
    )
    parser.add_argument(
        "--label-suffix",
        default="",
        help="Appended to each row's assertion, to distinguish an arm that is not the reported comparison",
    )
    return parser.parse_args()


def format_points(value: object) -> str:
    """Render a percentage-point value, or a dash when the metric was not comparable."""
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def comparison_rows(document: dict, metric_names: list[str], label_suffix: str = "") -> list[str]:
    rows = []
    for comparison in document.get("comparisons") or []:
        label = str(comparison.get("cell") or "-") + label_suffix
        metrics = comparison.get("metrics") or {}

        expected_values = []
        observed_values = []
        magnitudes = []
        for metric_name in metric_names:
            record = metrics.get(metric_name) or {}
            expected_values.append(record.get("expected"))
            observed_values.append(record.get("observed"))
            deviation = record.get("deviation_percentage_points")
            if deviation is not None:
                magnitudes.append(abs(float(deviation)))

        # A cell whose metrics were all incomparable (recorded value absent or "N/A") carries no
        # result, so it is omitted rather than rendered as a row of dashes.
        if all(value is None for value in observed_values):
            continue

        # The negative-control arm has no recorded per-cell expectation, so say that rather than
        # printing a bare dash that reads like a missing value.
        if all(value is None for value in expected_values):
            expected_cell = "not in the recorded contract"
        else:
            expected_cell = " / ".join(format_points(value) for value in expected_values) + " pp"
        observed_cell = " / ".join(format_points(value) for value in observed_values) + " pp"
        if magnitudes:
            observed_cell += f" (max delta {max(magnitudes):.2f} pp)"
        rows.append(f"{label}|{expected_cell}|{observed_cell}|-")
    return rows


def main() -> int:
    arguments = parse_arguments()
    if not arguments.report.is_file():
        return 0
    try:
        document = json.loads(arguments.report.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(document, dict):
        return 0
    for row in comparison_rows(document, arguments.metrics, arguments.label_suffix):
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
