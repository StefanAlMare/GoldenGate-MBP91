# MacPorts on Golden Gate Intel — continuously updated ledger

[**English**](MACPORTS.md) · [**Română**](MACPORTS.ro.md) · [Build C](README.md) · [Machine-readable port ledger](ports.csv)

![MacPorts](https://img.shields.io/badge/MacPorts-2.12.7-315d85?style=flat-square)
![State](https://img.shields.io/badge/Build_status-In_progress-b77d31?style=flat-square)
![Inventory](https://img.shields.io/badge/Verified_port_inventory-Pending-505866?style=flat-square)

> **Why this matters:** MacPorts package archives for **Darwin 27 x86_64** are often unavailable, even when archives exist for Darwin 27 ARM64 or older Intel macOS versions. Our HAO-adapted **Apple CLT 27.2 / Clang 21 / linker and LTO** permits MacPorts 2.12.7 to compile and install packages from source on the actual Intel MacBookPro9,1. This was not possible with the initial unadapted CLT environment.

## Status at 23 November 2026

| Verification gate | State | Grounded evidence |
|:--|:--|:--|
| MacPorts base running on Golden Gate C | **PASS** | `port version` → `Version: 2.12.7` |
| Apple compiler/linker executable under normal commands | **PASS** | C, C++, LTO, make and Python physical test matrix |
| Source archive fallback and build pipeline | **WORKING** | MacPorts prints `Archive not available ... building locally` and invokes compiler |
| Some source-built ports complete successfully | **REPORTED BY OPERATOR** | Multiple tools/packages installed while long-running dependency build continues |
| Snapshot of `port installed` and requested ports | **PENDING** | Not received for Golden Gate C in a publication-safe form |
| Verified architecture, invocation and variants per port | **PENDING** | Must test individual installed binaries; no inferred port checklist |
| Full requested package set installed | **IN PROGRESS** | Active build still running when this milestone was published |

**No port names have been pre-marked complete.** A prior report enumerated 117 installed ports on the separate **Tahoe** volume. Those are **not** an inventory of Golden Gate C.

### Evidence for missing binary archives

The MacPorts CLI attempted Darwin 27 Intel archive endpoints and received unavailable-archive responses, then moved to locally building source dependencies. A 23 November physical observation found a running `clang` process within the MacPorts process tree (77.4% sampled CPU at 16:23). The current compiling port is not reliably identified by that snapshot alone.

## Update workflow — one row for each confirmed port

A port graduates through distinct **checked evidence gates**:

- [x] MacPorts **2.12.7** base available on experimental C.
- [x] Adapted Apple CLT/HAO compiles and links x86_64.
- [x] MacPorts can start the source-build fallback.
- [ ] Capture definitive **C-only** `port installed`, `port echo requested` and `port installed active` after the ongoing build.
- [ ] Add each port's **name**, **version**, **revision**, **variants**, **requested/dependency**, installed/active status and supporting log reference to [ports.csv](ports.csv).
- [ ] Mark **build PASS** only after the relevant MacPorts build finishes with exit 0.
- [ ] Mark **runtime PASS** only after an installed x86_64 program or library's representative operation is checked.
- [ ] Publish a final package summary with package count and failures **only when the current operation completes**.

### Current verified-port table

| Port | Version / variants | Build | Installed & active | Runtime tested | Evidence |
|:--|:--|:--|:--|:--|:--|
| *Awaiting definitive Golden Gate C inventory* | — | — | — | — | `ports.csv` is intentionally unpopulated |

This is a **deliberately incomplete registry**, not a claim that no packages installed. The operator has explicitly observed successful installations; the specific list will be added only from original receipts.

## How to add verified packages later

Run [collect-macports.sh](collect-macports.sh) **after** an installation batch ends. It creates a local report and does not modify MacPorts or boot state. Compare the report with MacPorts build logs, check actual binaries and then append a single row to `ports.csv`. Update the table above and the project README milestone counts without rewriting historical events.

For each added row, make `build_status` and `runtime_status` explicit, e.g. `PASS`, `FAIL` or `PENDING`, instead of interpreting “active” as a successful functional test. Preserve failures and retries in the [chronological record](CHRONOLOGY.md) with the timestamp.

### MacPorts versus platform compatibility

MacPorts' default `buildfromsource ifneeded` policy can try a compatible archive first and build locally when none matches. Binary packages must match relevant platform/arch, versions, variants and prefix; Darwin 25 Intel archives are **not automatically** valid on Darwin 27 Intel. Source-built archives can be cached or later produced on faster compatible Intel machines after ABI/deployment checks.

**No Homebrew dependency is required for the verified C toolchain.**
