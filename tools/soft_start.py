#!/usr/bin/env python3
"""D13 / Q3 soft-start design — the gate network that bounds inrush SOA.

Backs plan §3.2.5's recommendation to slow the ramp from ~10 ms to ~50 ms,
which nothing had actioned. The point of the soft start is NOT to protect the
key switch contacts (they carry ~0.25 mA of gate drive); it is that the inrush
energy has to go somewhere, and the soft start deliberately puts it in the
MOSFET. So the MOSFET is selected on SOA, and the ramp time is the cheapest
margin available anywhere in this design.

⚠️ SOA has five limits -- R_DS(on), current, maximum power, THERMAL
INSTABILITY (Spirito) and BV_DSS -- and V_DS/I_D headline numbers cover two.
Slowing the ramp helps most in the high-V_DS / low-I_D Spirito corner, where
the limit is local current density, so less current at high V_DS is strictly
better.

⛔ This computes the ELECTRICAL TARGETS rigorously. It does NOT clear the part
against its SOA curve at the longer pulse: the published line is 10 ms, a
50 ms ramp needs the 25 ms equivalent, and a 1 ms curve cannot be scaled to
10 ms because the Spirito inflexion moves to LOWER V_DS as the pulse lengthens.
That check needs the datasheet plot read by eye.

    python3 tools/soft_start.py
"""

# ── the load the switch has to charge ───────────────────────────────────────
C_DOWNSTREAM_UF = 440.0   # C1 + C2, both EKXJ221ELL221MM25S (plan §3.2.5)
V_PACK_FULL = 84.0        # worst case for stored energy
V_LVC = 60.0              # worst case for current: constant-power load
I_LOAD_LVC = 0.62         # measured module draw at the LVC (plan §3.2.3)

# ── the MOSFET ──────────────────────────────────────────────────────────────
PART = "IXTP26P20P"
VGS_MAX = 20.0            # ±20 V gate rating -> the zener must clamp inside it
T_JMAX = 150.0
T_AMBIENT = 60.0          # plan's assumption; ⚠️ re-check once the box is sited

# ── TDK's limit on how FAST we may go ───────────────────────────────────────
DVDT_LIMIT_V_PER_US = 10.0   # CN150B110 input dv/dt maximum


def design(ramp_ms: float) -> dict:
    """Electrical targets for one ramp time."""
    ramp_s = ramp_ms / 1000.0
    dvdt = V_PACK_FULL / ramp_s                       # V/s
    i_charge = C_DOWNSTREAM_UF * 1e-6 * dvdt          # I = C dV/dt
    i_total = i_charge + I_LOAD_LVC
    # Peak dissipation: V_DS falls linearly at roughly constant I_DS, so the
    # equal-energy square pulse is P_MAX at t1/2 -- read the SOA curve at HALF
    # the ramp, at FULL V_DS. Reading the full-ramp line at average V_DS
    # understates the demand by 2x.
    p_peak = V_PACK_FULL * i_total
    return {
        "ramp_ms": ramp_ms,
        "dvdt_v_per_us": dvdt / 1e6,
        "i_charge": i_charge,
        "i_total": i_total,
        "p_peak": p_peak,
        "equiv_pulse_ms": ramp_ms / 2.0,
        "dvdt_headroom": DVDT_LIMIT_V_PER_US / (dvdt / 1e6),
    }


def energy_joules() -> tuple[float, float]:
    """Stored energy the MOSFET absorbs, and with the load drawing through."""
    e_cap = 0.5 * C_DOWNSTREAM_UF * 1e-6 * V_PACK_FULL ** 2
    return e_cap, e_cap * (1 + I_LOAD_LVC / (C_DOWNSTREAM_UF * 1e-6 * V_PACK_FULL / 0.050))


def derate_factor() -> float:
    """SOA plots are drawn at T_C = 25 °C. Derate linearly to T_JMAX."""
    return (T_JMAX - T_AMBIENT) / (T_JMAX - 25.0)


def gate_network(ramp_ms: float, r_gs_k: float = 100.0) -> dict:
    """The gate network that produces the ramp.

    Topology (plan §3.2.5, §6.2.2's discrete high-side at 84 V):

        source ── R_GS ──┬── gate        R_GS holds V_GS = 0 -> OFF
                         │               (the D14 default; a pull-down to
                         ├── C_GD ── drain   GROUND would turn it hard ON)
                         │
                         └── R_PD ── (key switch) ── low

    While the drain slews, the gate sits at its Miller plateau and essentially
    all of R_PD's current flows through C_GD, so the OUTPUT slew is set
    directly and deterministically:

        dV_drain/dt = I_pulldown / C_GD

    which is why the Miller cap -- not an RC into the gate -- is the component
    that actually fixes the ramp. An RC to the gate sets how fast V_GS moves;
    C_GD sets how fast the OUTPUT moves, and the output is what matters.
    """
    ramp_s = ramp_ms / 1000.0
    v_plateau = 10.0                       # ~V_GS in the plateau, P-ch
    i_pd = v_plateau / (r_gs_k * 1e3)      # the divider current, ~0.1 mA
    c_gd = i_pd * ramp_s / V_PACK_FULL     # C = I t / V
    return {
        "r_gs_k": r_gs_k,
        "i_pulldown_ua": i_pd * 1e6,
        "c_gd_nf": c_gd * 1e9,
        "zener_v": 15.0,
    }


if __name__ == "__main__":
    print(f"SOFT START — {PART}, {C_DOWNSTREAM_UF:.0f} µF downstream, "
          f"{V_PACK_FULL:.0f} V full charge\n")
    print(f"{'ramp':>7} {'dV/dt':>11} {'I chg':>7} {'I tot':>7} "
          f"{'P peak':>8} {'equiv':>9} {'TDK hdrm':>9}")
    print("-" * 64)
    for ms in (10, 25, 50, 100):
        d = design(ms)
        star = "  ⭐" if ms == 50 else ""
        print(f"{d['ramp_ms']:>5.0f}ms {d['dvdt_v_per_us']:>9.4f}V/µs "
              f"{d['i_charge']:>6.2f}A {d['i_total']:>6.2f}A "
              f"{d['p_peak']:>7.0f}W {d['equiv_pulse_ms']:>6.1f}ms "
              f"{d['dvdt_headroom']:>8.0f}x{star}")

    e_cap, _ = energy_joules()
    print(f"\nstored energy  ½CV² = {e_cap:.2f} J at {V_PACK_FULL:.0f} V")
    print(f"SOA derate for {T_AMBIENT:.0f} °C ambient: "
          f"×{derate_factor():.2f}  (plots are drawn at T_C = 25 °C)")

    print(f"\nGATE NETWORK for the 50 ms target:")
    g = gate_network(50)
    print(f"  R_GS            {g['r_gs_k']:.0f} kΩ gate-to-SOURCE  "
          f"(R110/R111 — the D14 bias-OFF)")
    print(f"  pulldown current {g['i_pulldown_ua']:.0f} µA")
    print(f"  C_GD            {g['c_gd_nf']:.1f} nF gate-to-DRAIN "
          f"(the Miller cap that FIXES the ramp)")
    print(f"  gate zener      {g['zener_v']:.0f} V  "
          f"(clamps |V_GS| inside the ±{VGS_MAX:.0f} V rating)")
    print(f"\n⛔ STILL OPEN: clear {PART} against its SOA curve at "
          f"{design(50)['p_peak']:.0f} W / {design(50)['equiv_pulse_ms']:.0f} ms,")
    print(f"   derated ×{derate_factor():.2f} → "
          f"{design(50)['p_peak']/derate_factor():.0f} W equivalent at 25 °C.")
    print(f"   The published line is 10 ms; a 25 ms pulse needs its own line, and")
    print(f"   a shorter curve CANNOT be scaled — the Spirito inflexion moves to")
    print(f"   lower V_DS as the pulse lengthens.")
