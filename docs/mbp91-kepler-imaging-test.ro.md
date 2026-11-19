# Probă pentru pictograme pe un al doilea disc USB, MacBookPro9,1

[English](mbp91-kepler-imaging-test.md) · Română

Martorul este SSD-ul extern de pe care MacBookPro9,1 pornește Golden 26B131 cu HAO `1547dcb`. Profilul experimental păstrează driverele ambelor plăci și omite două completări aduse de pachetul Kepler din Tahoe 25G229, în ImageIO și CMPhoto. Proba verifică dacă aceste componente comune influențează generarea sau afișarea pictogramelor. Lista operațiilor de instalare a fost verificată. Rămân de făcut asamblarea imaginii și pornirea pe MacBook.

## Pregătirea copiei

La pregătirea pachetului hardware se folosește profilul `tools/oclp-hardware/profiles/mbp91.json` de pe această ramură. Asamblarea începe din stadiul anterior aplicării pachetului grafic. Dacă profilul scurtat este aplicat peste un System deja populat, fișierele din cele două completări rămân pe disc. Se păstrează EFI-ul de 9,1, ambele drivere, același runtime HAO, același donor, același depozit de pictograme și aceleași două reguli `noauto`. Proba se face cu același cont și aceeași limbă.

Pentru candidat se folosește [rețeta inițială pentru cache-ul comun 26B131](../patches/golden-gate-userspace/src/prespecialization-26B131.json), cu amprenta SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`. Kitul existent de 9,1 folosește rețeta cu amprenta care începe cu `8e0669e2`. Aceasta adaugă exact ImageIO și CMPhoto la cele zece componente din lista inițială. Generatorul local a reprodus referința inițială pentru familia de cache A (`262FA161`). Înainte de scrierea discului de test, verificările constructorului trebuie să treacă pe sistemul și pe cache-ul imaginii candidate.

## Proba pe MacBook

Se notează ce placă grafică deservește ecranul intern. Pe fiecare instalare se deschide același volum și se verifică pictograma lui, răspunsul meniului Vizualizare din Finder și simbolurile Wi‑Fi și Bluetooth. Dacă sistemul comută plăcile, se repetă pe cealaltă placă. Se repetă și proba Metal pe NVIDIA. O schimbare a simptomelor ar indica cele două completări drept cauză posibilă. O probă ulterioară cu fiecare în parte le poate diferenția.
