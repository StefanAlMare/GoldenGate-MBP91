# Build C — Vremea și pictogramele din bara de meniu (25 noiembrie 2026)

[**Română**](WEATHER-MENUBAR-20261125.ro.md) · [**English**](WEATHER-MENUBAR-20261125.md) · [Build C](README.ro.md) · [Cronologie](CHRONOLOGY.ro.md)

**Calculator:** Golden Gate **27.2.1 (26B131)** pe **MacBookPro9,1** de 15″, cu Intel HD 4000, NVIDIA GT 650M și GMUX. Aceasta este starea actuală C; rapoartele A/B consemnează corect etapa mai veche în care Vremea nu pornea.

| Funcție | Rezultat pe ultimul snapshot C pornit |
|:--|:--|
| **Pornirea și stabilitatea Vremea** | **PASS:** aplicația pornește normal și nu se mai închide singură |
| **Fundal meteo animat** | **PASS:** vizibil, se modifică la schimbarea orașelor |
| **Prognoze și panouri meteo** | **PASS:** pagina principală, prognoza pe zile și cardurile testate afișează date |
| **Harta meteo mare** | **PASS:** funcționarea confirmată de operator |
| **Miniatura hărții meteo de pe pagina principală** | **DESCHIS:** mini-harta încă nu se redă complet; ultima problemă raportată din Vremea |
| **Pictograma bateriei** | **PASS vizual după restart:** orientare corectă, capătul bateriei spre dreapta |
| **Pictograma sunetului** | **PASS vizual după restart:** undele difuzorului spre dreapta |

**Dovadă:** captura reală din **25 noiembrie, 23:29:29 EET**, prezintă aplicația Vremea deschisă în română, cu prognoze și panouri populate și pictogramele bateriei/sunetului în bara de meniu. Observațiile fizice Work4 confirmă suplimentar fundalul animat și harta mare. Captura a fost oferită privat și **nu este redistribuită în repository**.

**Limite tehnice:** Work3/Work4 au comparat traseele grafice Intel și NVIDIA/Kepler. Miniatura a rămas incompletă inclusiv în probele cu Intel; funcționarea hărții mari sau a unei probe grafice nu validează automat mini-harta. Cauza precisă nu este confirmată. Această actualizare documentează rezultate, **nu pretinde publicarea unui patch sursă nou**.

**În continuare deschise separat:** simbolurile Wi-Fi/Bluetooth, graficele și precizia indicatorilor bateriei, Control Center, montarea NTFS/exFAT, deconectarea HDMI prin hubul Thunderbolt și unele artefacte NVIDIA. Orientarea corectă a unei pictograme nu demonstrează exactitatea nivelului bateriei. Installerul general și suportul altor modele rămân experimentale.

**Credite:** arhitectura HAO originală îi aparține lui [lythka](https://github.com/lythka/hao-patcher); sunt utilizate și componente OpenCore/OCLP/Tahoe. Adaptarea pentru MacBookPro9,1 și validarea pe hardware îi aparțin lui [StefanAlMare](https://github.com/StefanAlMare), cu asistență Codex. Nu publicăm componente Apple sau jurnale private.
