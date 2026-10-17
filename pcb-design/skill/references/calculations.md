# Calculations — template and standard set

Every calculation in a project goes into `docs/calculations.md` using
this entry format. Numbers without a source are opinions; opinions do
not go into a BOM.

## Entry template

```markdown
### C-07 LDO dissipation, U3 (AP2112K-3.3)

**Purpose:** verify U3 stays within rating at worst case.
**Formula:** P = (Vin − Vout) · Iout ; Tj = Ta + P · RθJA
**Inputs:**
- Vin max = 5.25 V (USB VBUS spec, docs/requirements.md §3)
- Iout max = 180 mA (power-budget table, rail +3V3 peak)
- RθJA = 250 K/W (AP2112 datasheet p.5, SOT-23-5, JEDEC board)
- Ta = 60 °C (skill default: inside-enclosure worst case)
**Result:** P = 1.95 V · 0.18 A = 0.351 W → Tj = 60 + 88 = 148 °C
**Margin:** Tj max 125 °C → **FAIL** by 23 K.
**Decision:** switch to buck (TPS62840) or add copper/thermal vias and
re-check with RθJA ≈ 150 K/W → Tj = 113 °C, 12 K margin → acceptable
only with the copper area; preferred: buck. → see C-08.
```

Numbering `C-nn`, referenced from schematic notes and design notes.
A failing calculation is kept in the file with its decision — it
documents why the design is what it is.

## Rules learned the hard way

- **Every thermal figure names its copper condition.** R_θJA is a
  property of the test board, not the part: write "R_θJA = 42 K/W
  (JEDEC 2s2p, 4L, 2 oz, 1 in²)" and then either reproduce that copper
  or recompute with a 1 oz / 2L / actual-area value (vendor app notes,
  or a thermal estimate from copper area). Tj at stall decides, not Tj
  at nominal.
- **Every error term has a sign.** DC-bias of a timing cap shortens or
  lengthens — derive which; bias current pulls up or down; hysteresis
  is the datasheet's value for the fitted vendor.
- **Fuses are checked on the time-current curve** against each fault
  current they are claimed to cover, and against the legitimate peak
  (stall, inrush) for nuisance trips. A 40 A fuse does not "cover" a
  10–20 A shorted FET.
- **Indicators are calculated for the fault they exist for** (open
  load, blown fuse): V_F of the actual LED colour, amplifier gain,
  threshold — "lit" and "dark" are numbers.
- **Per-resistor power** in the worst *held* state (button pressed,
  fault present), vs. the package rating derated at `calc_ambient`.
- **Power-path resistance from the real fills**, including thermal
  reliefs and the last millimetres into the pins; a centreline estimate
  of 2.1 mΩ was 3.4 mΩ when solved on the fill, and the pin thread was
  the worst part of it.

## Standard assumptions (skill defaults)

- Ambient for thermal calcs: **+60 °C** (board inside an enclosure in
  the sun). Override per project in `requirements.md`.
- Component ratings: industrial, −40 … +85 °C.
- Derating targets: capacitors ≤ 50 % of rated voltage (ceramic DC
  bias!), resistors ≤ 50 % of rated power, semiconductors Tj ≤ 80 %
  of max, inductors Isat ≥ 1.3 × peak current.
- Supply tolerances: USB VBUS 4.75–5.25 V; LiFePO4 cell 2.5–3.65 V
  (nominal 3.2 V); Li-ion 3.0–4.2 V.

## Standard calculations (do the ones that apply)

**Regulator dissipation & headroom** — as above. For bucks: efficiency
from the datasheet curve at the actual load, inductor ripple current
ΔI = (Vin − Vout)·D / (f·L), Isat ≥ Iout + ΔI/2 with margin.

**Trace width vs. current** — IPC-2221 for external layers:
I = k · ΔT^0.44 · A^0.725 (k = 0.048 external, 0.024 internal, A in
mil², ΔT in K). Use ΔT = 10 K at Ta = 60 °C. Document width, copper
weight and layer. For pours, state the narrowest neck.

**Bulk capacitance** — C ≥ I·Δt / ΔV for the load step and
C ≥ Iripple / (2π·f·ΔV) for switching ripple; then **derate ceramics**
for DC bias from the manufacturer's curve (a 10 µF 0603 X5R at 5 V can
be 3–4 µF). State effective capacitance.

**LED resistor** — R = (Vsupply − Vf) / If; P = If²·R; choose If for
the visual purpose (status LEDs 1–3 mA are plenty with modern LEDs).

**Voltage divider** — ratio, source impedance vs. ADC input impedance
(ADC sample cap ⇒ R_source ≤ datasheet limit or add a cap), quiescent
current for battery boards.

**Pull-ups** — I²C: R_min = (Vdd − 0.4 V)/3 mA, R_max = t_r /
(0.8473 · C_bus); choose inside the window; open-drain outputs likewise.

**Crystal load caps** — C1 = C2 = 2·(CL − Cstray), Cstray ≈ 3–5 pF per
side; check drive level and series resistance vs. datasheet.

**Fuse / polyfuse** — hold current ≥ 1.25 × max continuous, trip
current < wire/connector/trace rating, at +60 °C derating from the
datasheet table.

**Battery charge current** — per cell datasheet (LiFePO4 typically
0.5 C standard, 1 C max); charger IC programming resistor; thermal
check of the charger at Vin max and Ichg.

**Battery life** — per the power-budget table: average current → hours at
usable capacity (80 % of nominal for LiFePO4 at 0.1 C and 20 °C;
derate further for cold).

**RC filters** — f_c = 1/(2πRC); state intent (anti-alias, debounce,
EMI) and the resulting delay.

**Impedance** — JLC impedance calculator for the stack at order time:
USB 90 Ω diff, RF 50 Ω single; record width, gap, reference layer.

**Antenna / matching** — only when designing a matching network:
source and load impedances from datasheet, component values, and the
note that it needs VNA tuning on real hardware.

**Igniter / actuator current paths (safety-relevant boards only)** —
switch SOA, shunt sizing, measurement resolution, wire resistance at
max length, worst-case loop current — part of the FMEA.

## Power budget

A table per rail and per regulator (template in `doc-templates.md`),
at `calc_ambient`; it feeds the regulator and cell-current entries.

## Added in v0.2

**Power-path resistance budget** — for every current-carrying path
(cell → regulator, regulator → load, return): sum trace/pour resistance
(R = ρ·L/(w·t), ρ_Cu = 1.72e-8 Ω·m, 1 oz ≈ 35 µm) plus vias and
connectors; compare with the source's own resistance and the allowed
drop at peak current. Target: PCB path ≤ 0.5 × source resistance for
battery boards. Net class per segment follows from this, not from the
narrowest pad. A 52 mm path at 0.3 mm/1 oz is ≈ 86 mΩ — 2–3 × an AA
cell's resistance — and was missed by three audits once.

**Cell current from rail current** — I_cell = I_rail · V_rail /
(V_cell · η(I_rail, V_cell)); use the efficiency curve at the actual
light-load point (PFM region), not the headline figure. Add quiescent
currents of everything permanently on the rail and the divider/FB
leakage. State the result at nominal and at cell-empty voltage.

**Leakage against µA budgets** — Zener/TVS/ESD leakage at the working
voltage (a 5.6 V Zener on 3.3 V leaks tens of µA warm), FB-pin leakage
× divider impedance error, cap leakage for large ceramics/tantalums.

**Precision front end** — PGA common-mode window for each state
(sources on/off), with margin in mV; IDAC compliance at max R_load;
resolution vs. noise table at the chosen data rate and gain; burn-out
source behaviour with the actual RC filter at max gain.

**Igniter / safety-relevant paths** — current-path analysis over the
return ("every current must pass R_REF or ≥ x Ω into an IC pin");
worst single fault and worst double fault in mA; stored energy
∫i²dt of every capacitor that can discharge into the output vs. the
minimum fire pulse; state "arbitrary firmware + one hardware fault".
Results go into the FMEA and `docs/key-values.md`.
