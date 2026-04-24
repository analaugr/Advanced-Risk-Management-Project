# Section 4 - Base Model (correct implementation)
# SR 11-7 MBS S-Curve Validation 
# inputs from model_inputs.csv, LSEG (3133BTYD6), PMMS 04/16/2026

import math


# ---------------------------------------------------------------------------
# inputs
# all values converted to decimals here; formulas below use decimals throughout
# ---------------------------------------------------------------------------

MORT_RATE = 0.0630        # 6.30%  - Freddie Mac PMMS 04/16/2026
WAC       = 0.06492       # 6.492% - LSEG / CUSIP sheet
WAM       = 315           # months remaining - LSEG
OAS       = 104.8 / 1e4  # 104.8 bps converted to decimal - LSEG analytics
BALANCE   = 78_682_639.93 # current pool UPB - LSEG
CPR_MAX   = 0.60          # 60% ceiling per doc section 3.1

# two parameter sets are run:
#   default    - doc values (k=2.0, x0=1.0)
#   calibrated - x0 solved analytically to match LSEG's observed 17.2% CPR
#                keeping k=2.0 in range. derivation: x0 = x + ln(CPR_max/target - 1) / k
#                see limitations note at the bottom for why the gap exists
PARAMS = {
    "default":    {"k": 2.0, "x0": 1.0},
    "calibrated": {"k": 2.0, "x0": 0.6478},
}


# ---------------------------------------------------------------------------
# functions
# ---------------------------------------------------------------------------

def s_curve_cpr(mort_rate, wac, cpr_max, k, x0):
    # logistic S-curve from doc section 3.1, step 1
    # incentive is WAC minus current rate, in percentage points
    incentive = (wac - mort_rate) * 100
    return cpr_max / (1 + math.exp(-k * (incentive - x0)))


def to_smm(cpr):
    # converts annualized CPR to single monthly mortality, doc section 3.1 step 2
    return 1 - (1 - cpr) ** (1 / 12)


def build_cash_flows(balance, wac, wam, smm):
    # projects monthly cash flows per doc section 3.1 step 3
    # assumption: WAC and WAM are held constant over the pool life
    r   = wac / 12
    bal = balance
    cfs = []

    for t in range(1, wam + 1):
        n = wam - t + 1

        if n > 1:
            pmt   = bal * r / (1 - (1 + r) ** -n)
            sched = pmt - bal * r
        else:
            # final period: remaining balance is the scheduled principal
            sched = bal

        # clamp to avoid floating point producing a slightly negative value
        # in the last few periods
        sched = min(max(sched, 0.0), bal)

        prepay   = smm * (bal - sched)
        interest = bal * r

        cfs.append(sched + prepay + interest)
        bal -= sched + prepay

        if bal < 0.01:
            break

    return cfs


def price_mbs(cash_flows, wac, oas, balance):
    # Simpson's rule with h=1 month, per doc section 3.1 step 4
    # discount rate is (WAC + OAS) / 12 per the model spec
    # limitations note below re: why this differs from LSEG's implied yield
    disc = (wac + oas) / 12
    n    = len(cash_flows)
    dcf  = [cash_flows[t] / (1 + disc) ** (t + 1) for t in range(n)]

    # Simpson's requires an odd number of points (even intervals)
    # WAM=315 is odd so a full run gives 315 points - even intervals, no issue
    # if the pool exits early with an even point count, the last interval
    # falls back to trapezoidal per the doc's guidance
    if n % 2 == 1:
        end, use_trap = n, False
    else:
        end, use_trap = n - 1, True

    total = 0.0
    for i in range(end):
        if i == 0 or i == end - 1:
            c = 1
        elif i % 2 == 1:
            c = 4
        else:
            c = 2
        total += c * dcf[i]

    pv = total / 3.0

    if use_trap:
        pv += 0.5 * (dcf[end - 1] + dcf[n - 1])

    return (pv / balance) * 100, pv


def run(k, x0):
    cpr         = s_curve_cpr(MORT_RATE, WAC, CPR_MAX, k, x0)
    smm         = to_smm(cpr)
    cfs         = build_cash_flows(BALANCE, WAC, WAM, smm)
    price, pv   = price_mbs(cfs, WAC, OAS, BALANCE)
    return cpr, smm, cfs, price, pv


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    incentive = (WAC - MORT_RATE) * 100
    lseg_mid  = (101.2828 + 101.3128) / 2

    print("Base Model - correct S-curve implementation")
    print("Section 4 | Syonna | SR 11-7 MBS Validation\n")

    print("Inputs")
    print(f"  mortgage rate : {MORT_RATE*100:.2f}%  (PMMS 04/16/2026)")
    print(f"  WAC           : {WAC*100:.3f}%")
    print(f"  WAM           : {WAM} months")
    print(f"  OAS           : {OAS*1e4:.1f} bp")
    print(f"  balance       : ${BALANCE:,.2f}")
    print(f"  incentive     : {incentive:.3f}%  (WAC - current rate)\n")

    for label, p in PARAMS.items():
        cpr, smm, cfs, price, pv = run(p["k"], p["x0"])
        print(f"  [{label}]  k={p['k']}, x0={p['x0']}")
        print(f"  CPR           : {cpr*100:.4f}%")
        print(f"  SMM           : {smm*100:.4f}%")
        print(f"  months run    : {len(cfs)}")
        print(f"  disc rate/mo  : {(WAC+OAS)/12*100:.4f}%")
        print(f"  PV            : ${pv:,.2f}")
        print(f"  price         : {price:.4f}  (% of par)")
        print(f"  vs LSEG mid   : {price - lseg_mid:+.4f} pts\n")

    print("LSEG reference (04/17/2026)")
    print(f"  bid / ask     : 101.2828 / 101.3128  (mid {lseg_mid:.4f})")
    print(f"  realised CPR  : 17.2% (1M)")
    print(f"  implied yield : 5.1275%\n")

    print("Limitations")
    print(f"""
  1. discount rate
     model discounts at (WAC + OAS)/12 = {(WAC+OAS)*100:.2f}% annualized.
     LSEG prices at the implied yield of 5.13%. the spec uses WAC as
     the base rate but WAC is the pool coupon, not a risk-free rate.
     standard OAS convention uses the treasury/swap curve as the base
     (~3.84% implied from LSEG's OTR spread of 128.9 bps over TSY5Y).
     the ~{(WAC+OAS)*100 - 5.1275:.1f}% gap in discount rates explains most of the
     pricing difference vs market. flagged for SR 11-7 review.

  2. CPR vs LSEG
     default params give CPR ~10% at 0.192% incentive. LSEG shows
     17.2% realized. calibrated x0=0.6478 matches 17.2% but does not
     close the price gap - the discount rate issue dominates.
     also worth noting: LSEG's 17.2% includes turnover and relocation
     prepayments; the S-curve only models the refinancing channel.

  3. WAM / Simpson's parity
     WAM=315 is odd so a full run produces 315 points (even intervals,
     pure Simpson's). trapezoidal fallback only applies on early exit.
""")
