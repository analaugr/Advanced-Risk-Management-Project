"""
Outcome Analysis

Validation subtasks:
1) Stress scenarios within economically plausible / mathematically valid bounds
(Stress on isolated variables and joint scenarios)
2) Absolute boundary scenarios where the code or math starts to break.

Output:
- prints table of stress and boundary results
- saves outcome_analysis_results.csv

"""

import csv
import math
from copy import deepcopy
from typing import Any, Dict, List

import base_model as bm


def run_base_model_scenario(
    name: str,
    scenario_type: str,
    mort_rate: float = bm.MORT_RATE,
    wac: float = bm.WAC,
    wam: int = bm.WAM,
    oas: float = bm.OAS,
    balance: float = bm.BALANCE,
    cpr_max: float = bm.CPR_MAX,
    k: float = bm.PARAMS["default"]["k"],
    x0: float = bm.PARAMS["default"]["x0"],
    note: str = "",
) -> Dict[str, Any]:
    """
    Runs one scenario using the functions in base_model.py.
    Price is returned as % of par: PV / balance * 100.
    Boundary errors are caught so one bad case does not stop the script.
    """

    out = {
        "scenario_type": scenario_type,
        "scenario": name,
        "status": "OK",
        "note": note,
        "mort_rate_pct": mort_rate * 100,
        "wac_pct": wac * 100,
        "incentive_bps": (wac - mort_rate) * 10_000,
        "oas_bps": oas * 10_000,
        "wam_months": wam,
        "balance": balance,
        "cpr_max_pct": cpr_max * 100,
        "k": k,
        "x0": x0,
        "cpr_pct": "",
        "smm_pct": "",
        "months_run": "",
        "pv": "",
        "price_pct_par": "",
        "price_change_vs_base": "",
        "error_message": "",
    }

    try:
        if balance <= 0:
            raise ValueError("Balance must be positive because price = PV / balance * 100.")
        if wam < 0:
            raise ValueError("WAM cannot be negative.")
        if cpr_max < 0:
            raise ValueError("CPR_MAX cannot be negative.")

        cpr = bm.s_curve_cpr(mort_rate, wac, cpr_max, k, x0)
        smm = bm.to_smm(cpr)

        if isinstance(smm, complex):
            raise ValueError("SMM became complex because CPR exceeded 100%.")
        if not math.isfinite(smm):
            raise ValueError("SMM is not finite.")

        cash_flows = bm.build_cash_flows(balance, wac, wam, smm)
        if len(cash_flows) == 0:
            raise ValueError("No cash flows were generated. This usually happens at WAM = 0.")

        price, pv = bm.price_mbs(cash_flows, wac, oas, balance)

        if isinstance(price, complex) or isinstance(pv, complex):
            raise ValueError("Price/PV became complex.")
        if not math.isfinite(price) or not math.isfinite(pv):
            raise ValueError("Price/PV is not finite.")

        out.update({
            "cpr_pct": cpr * 100,
            "smm_pct": smm * 100,
            "months_run": len(cash_flows),
            "pv": pv,
            "price_pct_par": price,
        })

    except Exception as e:
        out["status"] = "BREAKS"
        out["error_message"] = str(e)

    return out


def build_stress_scenarios() -> List[Dict[str, Any]]:
    """Extreme but still economically interpretable and mathematically valid."""
    return [
        {"name": "Base case", "scenario_type": "stress_within_bounds", "note": "Original base-model inputs."},
        {"name": "Severe rate rally: +400 bps incentive", "scenario_type": "stress_within_bounds", "mort_rate": bm.WAC - 0.04, "note": "Mortgage rates fall far below WAC."},
        {"name": "Severe rate sell-off: -400 bps incentive", "scenario_type": "stress_within_bounds", "mort_rate": bm.WAC + 0.04, "note": "Mortgage rates rise far above WAC."},
        {"name": "Zero OAS", "scenario_type": "stress_within_bounds", "oas": 0.0, "note": "Lower discount-spread bound."},
        {"name": "Severe OAS widening: 500 bps", "scenario_type": "stress_within_bounds", "oas": 500 / 10_000, "note": "Liquidity/risk-premium stress."},
        {"name": "Flat S-curve: k = 0.1", "scenario_type": "stress_within_bounds", "k": 0.1, "note": "Weak prepayment response."},
        {"name": "Very steep S-curve: k = 10", "scenario_type": "stress_within_bounds", "k": 10.0, "note": "Threshold-like prepayment response."},
        {"name": "Burnout: CPR max = 10%", "scenario_type": "stress_within_bounds", "cpr_max": 0.10, "note": "Low prepayment ceiling."},
        {"name": "No burnout theoretical ceiling: CPR max = 100%", "scenario_type": "stress_within_bounds", "cpr_max": 1.00, "note": "Upper CPR ceiling while SMM remains real-valued."},
        {"name": "Short WAM boundary that still works: WAM = 1", "scenario_type": "stress_within_bounds", "wam": 1, "note": "Shortest positive maturity."},
        {"name": "Full original mortgage term: WAM = 360", "scenario_type": "stress_within_bounds", "wam": 360, "note": "Long maturity stress."},
    ]


def build_boundary_scenarios() -> List[Dict[str, Any]]:
    """Absolute implementation/math boundaries, including breakpoints."""
    return [
        {"name": "Lower WAM bound that works: WAM = 1", "scenario_type": "absolute_boundary", "wam": 1, "note": "Minimum positive WAM."},
        {"name": "Absolute lower WAM: WAM = 0", "scenario_type": "absolute_boundary", "wam": 0, "note": "Break point: no cash flows."},
        {"name": "Near-zero WAC that still works: WAC = 0.01 bp", "scenario_type": "absolute_boundary", "wac": 0.000001, "note": "Tiny but positive coupon."},
        {"name": "Absolute WAC lower bound: WAC = 0", "scenario_type": "absolute_boundary", "wac": 0.0, "note": "Break point for multi-month amortization formula."},
        {"name": "CPR max upper bound that works: CPR_MAX = 100%", "scenario_type": "absolute_boundary", "cpr_max": 1.0, "note": "SMM remains real-valued if actual CPR <= 100%."},
        {"name": "CPR max beyond bound: CPR_MAX = 120%", "scenario_type": "absolute_boundary", "cpr_max": 1.2, "note": "Can break if CPR exceeds 100%."},
        {"name": "Near-zero discount rate: WAC + OAS = 1 bp", "scenario_type": "absolute_boundary", "oas": 0.0001 - bm.WAC, "note": "Discounting valid but PV very high."},
        {"name": "Discount singularity: WAC + OAS = -1200% annual", "scenario_type": "absolute_boundary", "oas": -12.0 - bm.WAC, "note": "Break point: monthly discount denominator equals zero."},
        {"name": "Negative balance", "scenario_type": "absolute_boundary", "balance": -bm.BALANCE, "note": "Break point: price denominator is not meaningful."},
        {
            "name": "Rate rally + OAS widening",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC - 0.04,  # +400 bps incentive
            "oas": 300 / 1e4,  # spreads widen
            "note": "High refinance incentive + higher required return. Tests negative convexity under spread pressure."
        },

        {
            "name": "Rate sell-off + OAS widening",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC + 0.04,  # -400 bps incentive
            "oas": 300 / 1e4,
            "note": "Low CPR + higher discounting. Tests extension risk under stressed spreads."
        },

        {
            "name": "Rate rally + burnout",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC - 0.04,
            "cpr_max": 0.10,
            "note": "High incentive but limited refinancing capacity. Tests model behavior when S-curve ceiling binds."
        },

        {
            "name": "Rate rally + steep S-curve",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC - 0.04,
            "k": 10.0,
            "note": "Very sharp CPR response to incentive. Tests sensitivity to S-curve slope in favorable rate environments."
        },

        {
            "name": "Liquidity crisis",
            "scenario_type": "joint_stress",
            "oas": 500 / 1e4,
            "k": 0.1,
            "note": "Wide spreads + flat CPR response. Represents uncertainty and reduced refinancing activity."
        },

        {
            "name": "Extreme stress: rally + OAS widening + burnout",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC - 0.04,
            "oas": 400 / 1e4,
            "cpr_max": 0.10,
            "note": "Multiple stress factors combined. Tests model stability under severe but plausible conditions."
        },

        {
            "name": "Sell-off + long maturity",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC + 0.04,
            "wam": 360,
            "note": "Low CPR + long horizon. Tests extreme extension risk."
        },

        {
            "name": "Rally + short maturity",
            "scenario_type": "joint_stress",
            "mort_rate": bm.WAC - 0.04,
            "wam": 12,
            "note": "High CPR but limited remaining life. Tests cash-flow compression at short horizons."
        },
    ]


def run_scenario_set(scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for s in scenarios:
        kwargs = deepcopy(s)
        name = kwargs.pop("name")
        scenario_type = kwargs.pop("scenario_type")
        note = kwargs.pop("note", "")
        rows.append(run_base_model_scenario(name, scenario_type, note=note, **kwargs))
    return rows


def add_price_change_vs_base(rows: List[Dict[str, Any]]) -> None:
    base = next((r for r in rows if r["scenario"] == "Base case" and r["status"] == "OK"), None)
    if base is None:
        return
    base_price = base["price_pct_par"]
    for r in rows:
        if r["status"] == "OK" and r["price_pct_par"] != "":
            r["price_change_vs_base"] = r["price_pct_par"] - base_price


def fmt(x: Any, decimals: int = 4) -> str:
    if x == "" or x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.{decimals}f}"
    return str(x)


def print_table(rows: List[Dict[str, Any]]) -> None:
    cols = [
        "scenario_type", "scenario", "status", "incentive_bps", "oas_bps",
        "wam_months", "cpr_max_pct", "k", "cpr_pct", "smm_pct",
        "months_run", "price_pct_par", "price_change_vs_base", "error_message"
    ]
    widths = {c: max(len(c), *(len(fmt(r[c])) for r in rows)) for c in cols}
    print(" | ".join(c.ljust(widths[c]) for c in cols))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(" | ".join(fmt(r[c]).ljust(widths[c]) for c in cols))


def main() -> None:
    rows = run_scenario_set(build_stress_scenarios()) + run_scenario_set(build_boundary_scenarios())
    add_price_change_vs_base(rows)


    print("\n=== OUTCOME ANALYSIS RESULTS ===\n")
    print_table(rows)

    output_file = "outcome_analysis_results.csv"
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nFind full results to: {output_file}")


if __name__ == "__main__":
    main()
