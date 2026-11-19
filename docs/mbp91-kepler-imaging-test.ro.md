# Probă pentru pictograme pe un al doilea disc USB, MacBookPro9,1

[English](mbp91-kepler-imaging-test.md) · Română

Martorul este SSD-ul extern de pe care MacBookPro9,1 pornește Golden 26B131 cu HAO `1547dcb`. Profilul experimental păstrează driverele ambelor plăci și omite două completări aduse de pachetul Kepler din Tahoe 25G229, în ImageIO și CMPhoto. Proba verifică dacă aceste componente comune influențează generarea sau afișarea pictogramelor. Profilul și kitul separat de asamblare de pe iMac au fost verificate. Manifestul kitului cuprinde 36.077 de înregistrări și are amprenta SHA-256 `fb07b7b93fa70396e5ed322d7309a7fb1b5c48f0ef6a8a859bc1b5c46ae41a0a`. Urmează asamblarea locală, verificarea EFI și a condițiilor de pornire, apoi proba pe MacBook.

## Pregătirea copiei

La pregătirea pachetului hardware se folosește profilul `tools/oclp-hardware/profiles/mbp91.json` de pe această ramură. Asamblarea începe din stadiul anterior aplicării pachetului grafic. Dacă profilul scurtat este aplicat peste un System deja populat, fișierele din cele două completări rămân pe disc. Se păstrează EFI-ul de 9,1, ambele drivere, același runtime HAO, același donor, același depozit de pictograme și aceleași două reguli `noauto`. Proba se face cu același cont și aceeași limbă.

Pentru candidat se folosește [rețeta inițială pentru cache-ul comun 26B131](../patches/golden-gate-userspace/src/prespecialization-26B131.json), cu amprenta SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`. Kitul existent de 9,1 folosește rețeta cu amprenta care începe cu `8e0669e2`. Aceasta adaugă exact ImageIO și CMPhoto la cele zece componente din lista inițială. Generatorul local a reprodus referința inițială pentru familia de cache A (`262FA161`). Înainte de scrierea discului de test, verificările constructorului trebuie să treacă pe sistemul și pe cache-ul imaginii candidate.

## Proba pe MacBook

Se notează ce placă grafică deservește ecranul intern. Pe fiecare instalare se deschide același volum și se verifică pictograma lui, răspunsul meniului Vizualizare din Finder și simbolurile Wi‑Fi și Bluetooth. Dacă sistemul comută plăcile, se repetă pe cealaltă placă. Se repetă și proba Metal pe NVIDIA. O schimbare a simptomelor ar indica cele două completări drept cauză posibilă. O probă ulterioară cu fiecare în parte le poate diferenția.

### Verificarea operației grafice folosite de simboluri

[Adaptorul pentru framebuffer](../patches/golden-gate-metal-framebuffer/build/src/encoder.m) instalat în sistem se atașează clasei driverului Metal Intel `MTLIGAccelDevice`. Driverul GeForce din pachet nu are o dependență directă de acel adaptor. GT 650M a colorat o textură și a returnat corect toți cei 16 pixeli. Rămâne de verificat dacă poate citi corect culoarea existentă a pixelului în timpul execuției unui shader de fragment.

Pentru comparația plăcilor se rulează același test precompilat de citire din framebuffer și proba sa de control, care citește dintr-o textură. Se notează numele și ID-ul plăcii raportate chiar de utilitar, rezultatul comparării pixelilor și aspectul simbolului Wi-Fi. La fiecare pornire, utilitarul existent folosește placa Metal implicită. Două rezultate cu același ID testează o singură placă. Proba pe USB schimbă cele două componente comune de procesare a imaginilor. Ambele instalări păstrează aceleași adaptări pentru fiecare placă grafică.
