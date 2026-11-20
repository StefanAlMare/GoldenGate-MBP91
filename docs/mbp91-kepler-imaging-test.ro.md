# Probă pentru pictograme pe un al doilea disc USB, MacBookPro9,1

[English](mbp91-kepler-imaging-test.md) · Română

Martorul este SSD-ul extern de pe care MacBookPro9,1 pornește Golden 26B131 cu HAO `1547dcb`. Profilul experimental păstrează driverele ambelor plăci și omite două completări aduse de pachetul Kepler din Tahoe 25G229, în ImageIO și CMPhoto. Proba verifică dacă aceste componente comune influențează generarea sau afișarea pictogramelor. Profilul și kitul separat de asamblare de pe iMac au fost verificate. Manifestul kitului cuprinde 36.077 de înregistrări și are amprenta SHA-256 `fb07b7b93fa70396e5ed322d7309a7fb1b5c48f0ef6a8a859bc1b5c46ae41a0a`. Urmează asamblarea locală, verificarea EFI și a condițiilor de pornire, apoi proba pe MacBook.

## Pregătirea copiei

La pregătirea pachetului hardware se folosește profilul `tools/oclp-hardware/profiles/mbp91.json` de pe această ramură. Asamblarea începe din stadiul anterior aplicării pachetului grafic. Dacă profilul scurtat este aplicat peste un System deja populat, fișierele din cele două completări rămân pe disc. Se păstrează EFI-ul de 9,1, ambele drivere, același runtime HAO, același donor, același depozit de pictograme și aceleași două reguli `noauto`. Proba se face cu același cont și aceeași limbă.

Pentru candidat se folosește [rețeta inițială pentru cache-ul comun 26B131](../patches/golden-gate-userspace/src/prespecialization-26B131.json), cu amprenta SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`. Kitul existent de 9,1 folosește rețeta cu amprenta care începe cu `8e0669e2`. Aceasta adaugă exact ImageIO și CMPhoto la cele zece componente din lista inițială. Generatorul local a reprodus referința inițială pentru familia de cache A (`262FA161`). Înainte de scrierea discului de test, verificările constructorului trebuie să treacă pe sistemul și pe cache-ul imaginii candidate.

## Proba pe MacBook

Se notează ce placă grafică deservește ecranul intern. Pe fiecare instalare se deschide același volum și se verifică pictograma lui, răspunsul meniului Vizualizare din Finder și simbolurile Wi‑Fi și Bluetooth. Dacă sistemul comută plăcile, se repetă pe cealaltă placă. Se repetă și proba Metal pe NVIDIA. O schimbare a simptomelor ar indica cele două completări drept cauză posibilă. O probă ulterioară cu fiecare în parte le poate diferenția.

### Rezultatele fizice pe Golden 26B131

Pe 19 noiembrie 2026, două rulări pe MacBookPro9,1 cu runtime-ul local HAO `1547dcb` au întors rezultate identice. Un proces nativ x86_64 a selectat fiecare placă după identificatorul Metal și a desenat același contur Wi-Fi de 32 × 32, cu 175 de pixeli în simbol și 849 în fundal.

| Placă | Citire dintr-o textură separată | Citirea culorii din framebuffer în shader |
| --- | --- | --- |
| Intel HD Graphics 4000 | 1.024/1.024, eroare maximă 0/255 pe canal | 1.024/1.024, eroare maximă 0/255 pe canal |
| NVIDIA GeForce GT 650M | 1.024/1.024, eroare maximă 1/255 pe canal | La crearea pipeline-ului `fetch0`, compilatorul a returnat `CompilerError` 2, `Unhandled metadata type: air.render_target`. În această probă nu s-au produs pixeli. |

[Adaptorul autorului](../patches/golden-gate-metal-framebuffer/build/src/encoder.m) selectează clasa driverului Intel `MTLIGAccelDevice`. Prezența bibliotecii în procesul de testare nu identifică placa pe care a intervenit. Capturile Finder și IconServices au arătat pictograme de substituție și erori XPC. Legătura dintre o cerere Finder și eroarea shaderului NVIDIA rămâne de demonstrat.

Proba fizică a confirmat că varianta precompilată de autor pentru `fetch0` funcționează pe GT 650M cu texturi distincte pentru sursă și destinație. Driverul a raportat textura de intrare la indexul 127. Au corespuns toți cei 175 de pixeli ai simbolului și toți cei 849 ai fundalului, cu o eroare maximă de 1/255 pe canal. În aceeași sesiune compilatorul a refuzat din nou shaderul original. Proba a desenat în afara ecranului. GPU-ul folosit de WindowServer la autentificare, pictogramele vizibile și timpul de răspuns al Finder rămân de verificat.

Jurnalul autentificării din 19 noiembrie 2026 a înregistrat 33 de mesaje WindowServer selectate de un filtru larg după termeni grafici și de eroare în primele 30 de secunde ale procesului (16:30:37–16:31:07 EET). În aceste mesaje filtrul nu a identificat placa sau refuzul exact al shaderului. Următoarea citire a început la 16:31:26 EET. A numărat cel puțin 25.826 de intrări Finder cu eroarea 4097 la generarea imaginii și 25.914 refuzuri ale serviciului IconServices înainte de expirarea limitei de 90 de secunde. Sunt numărători de mesaje. Între intervale au rămas 19 secunde necitite, iar al doilea interval este incomplet.

Pe copia externă se păstrează același EFI, runtime, ImageIO și CMPhoto în ambele variante și se schimbă doar adaptarea Kepler. La prima autentificare se compară Wi-Fi și Bluetooth cu sunetul, Time Machine și eject. În aceeași fereastră Finder se verifică pictograma volumului Tahoe, timpul de răspuns și erorile de generare din IconServices înregistrate în acel interval. Experimentul separat cu cele două frameworkuri de imagine răspunde la o altă întrebare.
