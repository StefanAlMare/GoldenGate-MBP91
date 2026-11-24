# MacPorts 2.12.7 on Golden Gate Intel — 24 November 2026

[**English**](MACPORTS.md) · [**Română**](MACPORTS.ro.md) · [Build C](README.md) · [Complete CSV inventory](ports.csv)

> **15/15 selected BASIC ports installed and active; 173 unique MacPorts ports active in total.** Report captured on **24 November 2026, 09:57:40 EET**, on a **MacBookPro9,1**, Golden Gate **27.2.1 (26B131)**, x86_64, MacPorts **2.12.7**. This confirms installed/active inventory, **not** the source-build provenance or individual runtime behavior of all 173 ports.

| Metric | Verified from the operator-supplied inventory |
|:--|--:|
| Selected BASIC ports installed and active | **15/15** |
| Total distinct active ports | **173** |
| Additional active ports beyond BASIC selection | **158** |
| ICU (separately checked, within the 173 total) | **`icu @78.3_1`** |

## Selected BASIC set — all 15 active

| Port | Exact version / variants | Registry state |
|:--|:--|:--|
| `python314` | `@3.14.10_0+lto+optimizations` | **Installed / active** |
| `py314-pip` | `@26.2.2_0` | **Installed / active** |
| `git` | `@2.56.1_0+credential_osxkeychain+diff_highlight+doc+pcre+perl5_34` | **Installed / active** |
| `curl` | `@8.23.0_1+brotli+http2+idn+psl+ssl+zstd` | **Installed / active** |
| `wget` | `@1.25.0_1+gnutls` | **Installed / active** |
| `rsync` | `@3.5.1_0` | **Installed / active** |
| `jq` | `@1.8.2_0` | **Installed / active** |
| `htop` | `@3.5.3_0` | **Installed / active** |
| `tree` | `@2.3.2_0` | **Installed / active** |
| `coreutils` | `@9.12_0` | **Installed / active** |
| `xz` | `@5.8.4_0` | **Installed / active** |
| `zstd` | `@1.5.7_0` | **Installed / active** |
| `7zip` | `@26.06_0` | **Installed / active** |
| `smartmontools` | `@7.5_0+attributelog+savestates` | **Installed / active** |
| `iperf3` | `@3.22.1_0` | **Installed / active** |

All 15 names and versions also match the 173-entry registry list. The remaining 158 are other active ports in this environment; the source snapshot does **not** classify every one as a dependency rather than an independently requested port. The MacPorts `requested` flag itself has not been audited.

## Reproducible inventory

- [**Operator report, original 15-port check and 173-entry registry snapshot**](evidence/macports-basic-20261124.md). This is the evidence source for the counts and versions.
- [**Machine-readable inventory: 173 rows**](ports.csv) records name, version, revision, variants and installed/active state. Empty architecture fields and `NOT_AUDITED` / `NOT_TESTED` fields are deliberate: host architecture is known, individual binaries and source-build receipts are not independently certified.
- [**Read-only inventory collection script**](collect-macports.sh) supports later updates without modifying MacPorts or the boot volume.

**Chronology:** on **23 November**, the provisional checkpoint recorded **138 active ports**; `coreutils` was still being processed and an attempt to configure `wget` hit an HTTP 404. The **24 November** report supersedes that *current-state* figure: both `coreutils @9.12_0` and `wget @1.25.0_1+gnutls` are now listed installed/active. The previous incident remains in [the event log](CHRONOLOGY.md).

### What this proves — and what it does not

The HAO-adapted CLT/Clang toolchain on Intel has previously demonstrated working MacPorts source-build fallback; the **present report establishes 15 requested BASIC targets and 173 active installed ports**. It does **not** demonstrate that each of the 173 was individually compiled locally from source, or that all 173 passed application-level runtime tests. Track each future source-build exit code, binary architecture and smoke test independently; do not infer success merely from `active`.

Earlier counts from a separate Tahoe installation are **not** included. This is a Golden Gate macOS 27.2.1 / 26B131 inventory. Third-party components retain their respective licenses.
