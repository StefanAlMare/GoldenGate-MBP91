# Reparațiile și probele A/B pentru MacBookPro9,1

Sursele se citesc împreună cu ramura `golden-gate/mbp91-stage-1`. Directorul `diagnostics` păstrează sondele pentru Finder și IconServices, Dock, ferestre, bateria și bara de meniu, precum și uneltele pentru imaginea B și referința grafică Intel/NVIDIA. Sonda Finder–Elgato este experimentală. Nu s-a identificat un rezultat fizic documentat pentru ea. Manifestele fixează amprentele componentelor și ale imaginilor de referință.

Fișierele `.in` sunt șabloane inactive. Păstrează validările originale pentru model, build, utilizator, volume, snapshoturi, proveniența fișierelor și identitatea mediului USB. Valorile operatorului se completează din bonurile și inventarul propriu. Amprentele imaginilor A și B rămân cele originale. Copia locală rezultată include datele completate și se păstrează în afara depozitului.

Din directorul `golden-gate`, prima comandă afișează schema goală pentru profilul privat. A doua pregătește exclusiv fișiere, într-un director nou ales de operator.

```sh
python3 -IB Configureaza-sabloane-AB.py
python3 -IB Configureaza-sabloane-AB.py --profil /cale/privata/profil.json --destinatie /cale/privata/proba-AB
```

`UUID_A_PROTECTED_1` până la `UUID_A_PROTECTED_4` reprezintă celelalte patru identități protejate ale suportului A din inventarul original, pe lângă grupul A. Câmpurile `SNAPSHOT_ID` și `BLESS` provin din bonul aceleiași intervenții, pentru snapshotul respectiv. `B_IMAGE_DIRECTORY` numește dosarul asamblării istorice din `.work/b-kit-staging`. Scripturile care cer directoarele private de construcție și bonurile lor verifică și existența acestor intrări la utilizare. Pentru generatorul unităților de apel se setează `GOLDEN_GATE_RUNTIME_TOOLS` către directorul `tools` al runtime-ului verificat.

Probe pentru NTFS și exFAT, pe instalația B configurată · [ghidul de lucru](kit-volume/Citeste.md). Citirea inventarului, identificarea implementărilor, montarea explicită numai pentru citire, testul cu reguli `ro,auto` și jurnalul după login au rezultate distincte. Testele cu date sintetice se rulează din rădăcina depozitului.

```sh
python3 -IB -m unittest discover -s golden-gate/kit-volume -p 'test_*_b.py'
```
