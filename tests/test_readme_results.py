import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from report.readme_results import END, START, update_readme  # noqa: E402


def make_results(root):
    (root / "results/in_sample").mkdir(parents=True)
    (root / "results/oos").mkdir(parents=True)
    (root / "figures/issue10").mkdir(parents=True)
    pd.DataFrame({"t0": ["a", "b", "c"], "date": ["2025-01-02", "2025-01-02", "2025-01-03"]}).to_csv(
        root / "results/in_sample/events.csv", index=False)
    pd.DataFrame({"n": [40, 35], "mean_bp_30s": [1.25, -0.8], "t_30s": [2.1, -1.7]},
                 index=["follow", "fade"]).to_csv(root / "results/in_sample/regime_table.csv")
    pd.DataFrame({"in_sample": [75, 3.0, 2.0, 55.0, 12.5, 4.0, 19.5],
                  "out_of_sample": [30, 1.5, 0.9, 52.0, 12.5, 4.0, 18.0]},
                 index=["trades", "mean_pnl_usd", "t_day_clustered", "hit_rate_pct",
                        "mean_spread_cost_usd", "fees_per_trade_usd", "break_even_cost_usd"]
                 ).to_csv(root / "results/oos/summary.csv")
    (root / "results/oos/summary.md").write_text("| | in | out |\n|---|---|---|\n| trades | 75 | 30 |\n")
    (root / "figures/issue10/average_path.png").write_bytes(b"png")
    (root / "README.md").write_text("# Project\n\nIntro text.\n")


def test_block_has_numbers_tables_figures_and_prose(tmp_path):
    make_results(tmp_path)
    text = update_readme(tmp_path)
    assert text.startswith("# Project\n\nIntro text.") and text.count(START) == 1 and text.count(END) == 1
    assert "3 shocks on 2 trading days" in text
    assert "follow shocks (40) moved 1.25 bp" in text and "t = -1.70" in text
    assert "made $1.50 per contract per trade" in text and "$18.00 vs $16.50 paid" in text
    assert "![Average move after a shock, by regime](figures/issue10/average_path.png)" in text
    assert "figures/issue10/shocks_per_day.png" not in text  # missing figures are skipped
    assert "| trades | 75 | 30 |" in text and "### Limitations" in text


def test_rerunning_replaces_the_block_and_keeps_your_prose(tmp_path):
    make_results(tmp_path)
    update_readme(tmp_path)
    (tmp_path / "docs/findings.md").write_text("- H1 held in-sample but not out-of-sample.")
    with open(tmp_path / "README.md", "a") as f:
        f.write("\n## Contact\n")
    text = update_readme(tmp_path)
    assert text.count(START) == 1 and "H1 held in-sample" in text and text.rstrip().endswith("## Contact")
    assert update_readme(tmp_path) == text  # idempotent


def test_works_before_any_results_exist(tmp_path):
    (tmp_path / "README.md").write_text("# Project\n")
    assert "No results yet" in update_readme(tmp_path)
