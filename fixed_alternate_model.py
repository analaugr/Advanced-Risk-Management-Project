# Section 4 - Alternative Model (wrong/simplistic implementation)
# same inputs as base model - purpose is to quantify the pricing error
#
# three intentional errors per doc section 4.1:
#   1. linear CPR instead of logistic S-curve
#   2. trapezoidal rule h=3 (quarterly) instead of Simpson's monthly
#   3. discount at WAC only, OAS ignored

import math
import importlib.util
import os


# ---------------------------------------------------------------------------
# inputs - identical to base model
# ---------------------------------------------------------------------------

MORT_RATE = 0.0630
WAC       = 0.06492
WAM       = 315
OAS       = 104.8 / 1e4  # included for reference only, not used by this model
BALANCE   = 78_682_639.93

# linear scaling constant for CPR (error 1)
# chosen so CPR is in a plausible range at ~1% incentive
# structurally wrong because there is no ceiling and no S-shape
A = 8.0


# ---------------------------------------------------------------------------
# functions
# ---------------------------------------------------------------------------

def linear_cpr(mort_rate, wac, a):
    # error 1: replaces the S-curve with a linear function
    # assumption: CPR scales linearly with incentive, floored at 0
    # capped at 0.99 only to prevent a math error in the cash flow loop
    incentive = (wac - mort_rate) * 100
    return min(a * max(incentive, 0) / 100, 0.99)


def to_smm(cpr):
    return 1 - (1 - cpr) ** (1 / 12)


def build_cash_flows(balance, wac, wam, smm):
    # same cash flow mechanics as base model
    # assumption: WAC and WAM held constant
    r   = wac / 12
    bal = balance
    cfs = []

    for t in range(1, wam + 1):
        n = wam - t + 1

        if n > 1:
            pmt   = bal * r / (1 - (1 + r) ** -n)
            sched = pmt - bal * r
        else:
            sched = bal

        sched = min(max(sched, 0.0), bal)

        prepay   = smm * (bal - sched)
        interest = bal * r

        cfs.append(sched + prepay + interest)
        bal -= sched + prepay

        if bal < 0.01:
            break

    return cfs


def price_trapezoidal(cash_flows, wac, balance):
    # error 2: trapezoidal rule sampling every 3rd month instead of monthly
    # error 3: discount rate is WAC/12 only, OAS is excluded
    disc = wac / 12

    # sample quarterly; always include the last cash flow to avoid truncation
    idx = list(range(0, len(cash_flows), 3))
    if idx[-1] != len(cash_flows) - 1:
        idx.append(len(cash_flows) - 1)

    dcf   = [cash_flows[i] / (1 + disc) ** (i + 1) for i in idx]
    h     = 3
    total = dcf[0] + dcf[-1]
    for i in range(1, len(dcf) - 1):
        total += 2 * dcf[i]
    pv = (h / 2) * total

    return (pv / balance) * 100, pv


def load_base_prices():
    # loads base_model.py from the same directory for comparison
    # returns None if the file is not found
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_model.py")
    if not os.path.exists(path):
        return None

    spec = importlib.util.spec_from_file_location("base", path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)

    out = {}
    for label, p in base.PARAMS.items():
        cpr = base.s_curve_cpr(base.MORT_RATE, base.WAC, base.CPR_MAX, p["k"], p["x0"])
        smm = base.to_smm(cpr)
        cfs = base.build_cash_flows(base.BALANCE, base.WAC, base.WAM, smm)
        px, _ = base.price_mbs(cfs, base.WAC, base.OAS, base.BALANCE)
        out[label] = px
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    incentive = (WAC - MORT_RATE) * 100
    lseg_mid  = (101.2828 + 101.3128) / 2

    print("Alternative Model - wrong/simplistic implementation")
    print("(linear CPR | trapezoidal h=3 | no OAS)")
    print("Section 4 | Syonna | SR 11-7 MBS Validation\n")

    print("Inputs (same as base model)")
    print(f"  mortgage rate : {MORT_RATE*100:.2f}%")
    print(f"  WAC           : {WAC*100:.3f}%")
    print(f"  WAM           : {WAM} months")
    print(f"  OAS           : {OAS*1e4:.1f} bp  (ignored - error 3)")
    print(f"  balance       : ${BALANCE:,.2f}")
    print(f"  incentive     : {incentive:.3f}%")
    print(f"  linear slope  : {A}\n")

    cpr = linear_cpr(MORT_RATE, WAC, A)
    smm = to_smm(cpr)
    cfs = build_cash_flows(BALANCE, WAC, WAM, smm)
    price, pv = price_trapezoidal(cfs, WAC, BALANCE)

    print("Output")
    print(f"  CPR (linear)  : {cpr*100:.4f}%")
    print(f"  SMM           : {smm*100:.4f}%")
    print(f"  months run    : {len(cfs)}")
    print(f"  disc rate/mo  : {WAC/12*100:.4f}%  (WAC only)")
    print(f"  PV            : ${pv:,.2f}")
    print(f"  price         : {price:.4f}  (% of par)")
    print(f"  vs LSEG mid   : {price - lseg_mid:+.4f} pts\n")

    print("Comparison vs base model")
    base_prices = load_base_prices()
    if base_prices:
        for label, base_px in base_prices.items():
            err = (price - base_px) * 100
            print(f"  base ({label:11s}) : {base_px:.4f}")
            print(f"  alternative       : {price:.4f}")
            print(f"  error             : {err:+.1f} bps ({'over' if err > 0 else 'under'}-priced vs base)")
            print(f"  doc predicts      : 50-150 bps\n")
        print(f"  note: gap is wider than predicted because at {incentive:.3f}% incentive")
        print(f"  the linear model gives CPR = {cpr*100:.2f}% vs the S-curve's ~10%.")
        print(f"  errors 2 and 3 partially offset - low discount rate inflates PV")
        print(f"  while coarse sampling understates cash flows.")
    else:
        print("  place both files in the same folder to see comparison.\n")

    print(f"""
Error summary
  error 1 - linear CPR
    CPR = {A} x {incentive:.3f}% = {cpr*100:.2f}% (no ceiling, no S-shape)
    base model default gives ~10% at same inputs

  error 2 - trapezoidal h=3
    uses {len(list(range(0, len(cfs), 3)))} quarterly points vs {len(cfs)} monthly
    straight-line interpolation misses MBS cash flow curvature

  error 3 - no OAS
    discounting at {WAC/12*100:.4f}%/mo vs {(WAC+OAS)/12*100:.4f}%/mo in base model
    lower rate overstates PV
""")
