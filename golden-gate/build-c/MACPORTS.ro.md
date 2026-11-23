# MacPorts 2.12.7 pe Golden Gate Intel — registru actualizabil

[**Română**](MACPORTS.ro.md) · [**English**](MACPORTS.md) · [Prezentare C](README.ro.md) · [Porturi CSV](ports.csv)

![MacPorts](https://img.shields.io/badge/MacPorts-2.12.7-315d85?style=flat-square) ![În curs](https://img.shields.io/badge/Status-compilare_in_curs-b77d31?style=flat-square)

**Ce am realizat:** pachetele MacPorts nu se instalau normal pe Darwin 27 x86_64 din lipsa arhivelor binare compatibile și a unui toolchain Apple ARM funcțional prin HAO. Integrarea CLT **27.2 / Clang 21 / ld / LTO** permite acum compilarea și instalarea **din surse** pe MacBookPro9,1 Intel.

**Stare la 23 noiembrie:** MacPorts 2.12.7 funcționează, mai multe pachete au fost instalate conform operatorului, iar compilarea altora continuă. Un proces Clang activ a fost observat în arborele MacPorts. **Lista completă de porturi și versiuni nu este încă verificată**; nu inventăm nume și nu copiem cele 117 porturi de pe instalarea separată Tahoe.

## Procedura de completare

- [x] MacPorts 2.12.7 pornește: `port version` → `Version: 2.12.7`.
- [x] CLT/Clang/ld pe Intel compilează și linkează executabile x86_64.
- [x] MacPorts încearcă arhivele și trece la compilare din surse când nu sunt disponibile.
- [ ] După terminarea lotului curent, colectăm `port installed`, `port installed active` și `port echo requested` pe **Golden C**.
- [ ] Pentru fiecare port completăm [ports.csv](ports.csv): nume, versiune, revizie, variante, arhitectură, cerut sau dependență.
- [ ] Bifăm separat compilarea, instalarea, activarea și **testul de execuție**.
- [ ] Abia după probe publicăm raportul complet și numărul porturilor funcționale.

[Scriptul doar pentru citire](collect-macports.sh) produce un raport privat local. Nu instalează pachete și nu schimbă System, snapshot, EFI sau SIP. Pentru fiecare port nou păstrăm dovada relevantă și actualizăm tabelul fără a modifica retroactiv istoricul.

**Criteriu:** „instalat” nu înseamnă automat „testat funcțional”; un port poate fi compilat, instalat, activ sau verificat la rulare — stări distincte. Detalii complete: [MACPORTS.md](MACPORTS.md).
