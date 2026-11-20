# Golden Gate pe Mac Intel și Hackintosh

[English](README.md) · Română

Pentru mesaje în română, adaugă `--lang ro` ca primă opțiune la `./Inventar.command` și `python3 Pregateste-fstab.py`.

## Primul pas pentru un calculator nou

Deschide `Inventar.command` dintr-un macOS funcțional pe calculatorul care urmează să pornească Golden. Lasă conectate discurile pe care le vei folosi la probă. Inventarul citește metadatele prin `diskutil`, cu permisiunile utilizatorului. Raportul obișnuit poate fi copiat în fișa de caz. Identificatorii de forma `diskNsM` sunt valabili pentru pornirea curentă.

Pe MacBookPro9,1, Golden 26B131 a afișat Setup Assistant după ce două reguli specifice volumelor interne au oprit automontarea NTFS și exFAT. Pe un alt calculator, un volum NTFS sau exFAT care apare în inventar reprezintă un candidat la diagnostic. Notează întâi dacă prima configurare pornește normal. Pentru același simptom caută în captură atât așteptarea discului RAM la Setup, cât și cererea de montare rămasă în FSKit. O bară de progres oprită singură oferă prea puține informații pentru a atribui cauza.

## Pregătirea profilului

[Ghidul de inventar](Inventar.ro.md) arată cum se selectează explicit partițiile. [Ghidul de previzualizare fstab](Previzualizare-fstab.md) arată cum se generează cu Python 3 o propunere pornind de la copia fișierului `private/etc/fstab` de pe volumul Data Golden al țintei. Inventarul și previzualizarea pot fi folosite înainte de prima pornire, inclusiv din Tahoe. Regulile conțin UUID-urile sistemelor de fișiere de pe calculatorul respectiv. Identificatorii partițiilor GPT, numele de disc și etichetele volumelor au alte roluri.

Pachetul se oprește la previzualizare. Pentru prima aplicare pe un model nou se pregătește un profil reversibil pentru copia Golden, cu identificarea țintei System/Data și conservarea configurației inițiale. Pachetul de activare destinat MacBookPro9,1 are propriile identificatoare și se folosește doar pe configurația pentru care a fost construit.

## Montare manuală pe B

Din directorul kit-volume al copiei configurate local, cu MacBook-ul pornit în Golden B, rulează comanda de mai jos. Ea se conectează prin SSH la MacBook și verifică volumul de pornire, apoi caută UUID-urile sistemelor de fișiere NTFS și exFAT pe discul intern. Cere montare numai pentru citire și verifică dacă ambele volume pot fi accesate în aceeași sesiune.

```sh
/usr/bin/python3 -I -B "./Probeaza-volume-B.py" --monteaza-ro ambele
```

Cu opțiunea `--componente`, comanda citește cele două reguli din `/etc/fstab`, implementările declarate în pachetele Apple și cele două biblioteci LiveFiles din cache-ul Intel al sistemului pornit. Această opțiune nu solicită montare. Fără argumente, comanda face numai inventarul. La finalul probei de montare, volumele montate temporar sunt demontate în ordine inversă, dacă starea lor poate fi confirmată. La expirarea unei cereri, se repetă numai inventarul. Sistemul pornește în continuare cu regulile sale originale.

## Dovezi de păstrat

Completează [fișa calculatorului](Fisa-calculator.md) pentru fiecare combinație de hardware și build. Pe Hackintosh, notează placa de bază, controlerul de stocare, procesorul și GPU-ul reale, separat de SMBIOS. Înregistrează distinct prima fereastră Setup, desktopul, a doua pornire și accesul la date. Un profil local care conține UUID-uri rămâne în dosarul privat al calculatorului.

Un volum cu `ro,noauto` rămâne în afara automontării și după login. După confirmarea desktopului și a unei reporniri stabile, poți testa separat un singur volum printr-o cerere explicită de montare numai pentru citire. Starea `Open` din IORegistry, faptul că volumul a fost montat și citirea reușită a unui fișier sunt trei observații diferite.

### Proba de automontare la pornirea lui B

Cu MacBookPro9,1 pornit de pe SSD-ul B, se rulează pe iMac `/usr/bin/python3 -I -B Automontare-B.py activeaza` din acest director. Utilitarul identifică grupul APFS al lui B și suportul USB fizic, salvează fișierul inițial în `private/etc/fstab.golden-b-inainte-de-automontare` de pe Data B și schimbă cele două reguli în `ro,auto`. Recitește fișierul înainte de a afișa confirmarea `GG_BOOT B`. Operatorul repornește normal după confirmare.

La login, înaintea unei montări manuale, `/usr/bin/python3 -I -B Probeaza-volume-B.py --dupa-boot` consemnează ultima pornire, opțiunile din fstab și starea fiecărei partiții interne după UUID. Pentru volumele deja montate verifică modul de acces și încearcă să citească până la 4096 de octeți dintr-un fișier existent. Lipsa unui fișier eligibil lasă citirea neconfirmată. Prezența la login și restabilirea vechilor reguli sunt operații independente.

Pentru revenire, `/usr/bin/python3 -I -B Automontare-B.py revenire` restabilește prin SSH conținutul inițial. Dacă B nu ajunge la login sau SSH, se conectează SSD-ul fizic B la iMac și se folosește `revenire-usb`. În cazul în care conexiunea nu permite pregătirea inițială, `activeaza-usb` face aceeași modificare pe Data B deja montat la iMac. Ambele moduri USB verifică identitatea grupului B și apartenența la un suport USB fizic înainte de scriere. Copia inițială rămâne disponibilă pentru repetarea probei. Un fstab modificat ulterior se păstrează pentru revizuire.

Dacă volumele apar nemontate la login, `/usr/bin/python3 -I -B Probeaza-volume-B.py --jurnal-boot`, rulat pe iMac, folosește pornirea curentă a MacBook-ului. Afișează diferența în secunde dintre ultima scriere a fstab și pornire (negativă pentru scriere anterioară), regulile actuale și mesajele accesibile Disk Arbitration, FSKit și LiveFS din primele 20 de minute. Mesajele cu volum neidentificat rămân atribuite serviciului. Acest mod citește jurnalul și inventarul de discuri.
