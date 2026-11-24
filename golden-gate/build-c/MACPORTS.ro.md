# MacPorts 2.12.7 pe Golden Gate Intel — 24 noiembrie 2026

[**Română**](MACPORTS.ro.md) · [**English**](MACPORTS.md) · [Prezentarea Build C](README.ro.md) · [Inventar CSV](ports.csv)

> **15/15 porturi BASIC selectate sunt instalate și active. Inventarul MacPorts conține 173 de porturi active în total.** Raportul este din **24 noiembrie 2026, ora 09:57:40 EET**, de pe **MacBookPro9,1**, Golden Gate **27.2.1 (26B131)**, x86_64, MacPorts **2.12.7**. Acest document certifică starea din registrul de instalare, **nu** proveniența compilării din surse și nici testele individuale de funcționare.

| Indicator | Rezultat din raport |
|:--|--:|
| Porturi BASIC selectate, instalate și active | **15/15** |
| Porturi distincte active în total | **173** |
| Alte porturi active, în afara selecției BASIC | **158** |
| ICU (verificat separat; inclus în totalul de 173) | **`icu @78.3_1`** |

## Cele 15 porturi BASIC — toate active

| Port | Versiune / variante exacte | Stare |
|:--|:--|:--|
| `python314` | `@3.14.10_0+lto+optimizations` | **Instalat / activ** |
| `py314-pip` | `@26.2.2_0` | **Instalat / activ** |
| `git` | `@2.56.1_0+credential_osxkeychain+diff_highlight+doc+pcre+perl5_34` | **Instalat / activ** |
| `curl` | `@8.23.0_1+brotli+http2+idn+psl+ssl+zstd` | **Instalat / activ** |
| `wget` | `@1.25.0_1+gnutls` | **Instalat / activ** |
| `rsync` | `@3.5.1_0` | **Instalat / activ** |
| `jq` | `@1.8.2_0` | **Instalat / activ** |
| `htop` | `@3.5.3_0` | **Instalat / activ** |
| `tree` | `@2.3.2_0` | **Instalat / activ** |
| `coreutils` | `@9.12_0` | **Instalat / activ** |
| `xz` | `@5.8.4_0` | **Instalat / activ** |
| `zstd` | `@1.5.7_0` | **Instalat / activ** |
| `7zip` | `@26.06_0` | **Instalat / activ** |
| `smartmontools` | `@7.5_0+attributelog+savestates` | **Instalat / activ** |
| `iperf3` | `@3.22.1_0` | **Instalat / activ** |

Toate cele 15 apar și în lista celor 173, cu versiuni identice. Celelalte 158 de intrări includ pachete auxiliare, însă raportul nu dovedește că **fiecare** este exclusiv o dependență; nici marcajul MacPorts `requested` nu este verificat.

## Dovezi și actualizări

- [**Raportul operatorului: verificarea BASIC și toate cele 173 de intrări**](evidence/macports-basic-20261124.md).
- [**Inventarul complet editabil CSV, cu 173 de porturi**](ports.csv) păstrează versiunile, reviziile și variantele. `NOT_AUDITED` la compilare și `NOT_TESTED` la execuție sunt intenționate.
- [**Scriptul read-only**](collect-macports.sh) permite colectări ulterioare fără a modifica porturile instalate.

**Cronologie:** la 23 noiembrie erau raportate intermediar **138 de porturi active**, `coreutils` era în lucru și `wget` întâmpinase eroarea HTTP 404. Raportul nou din 24 noiembrie arată **`coreutils @9.12_0` și `wget @1.25.0_1+gnutls` instalate și active**. Eroarea veche rămâne în [jurnalul cronologic](CHRONOLOGY.ro.md), dar nu mai este prezentată drept situație curentă.

**Limită importantă:** am demonstrat funcționarea mecanismului de compilare MacPorts din surse prin CLT/HAO adaptat. Inventarul actual certifică **instalarea/activarea**, nu faptul că toate cele 173 de porturi au fost compilate individual din surse ori testate la rulare. Nu am importat în această evidență porturile de pe discul Tahoe.
