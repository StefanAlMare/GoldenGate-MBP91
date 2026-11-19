# Golden Gate pe Mac Intel și Hackintosh

[English](README.md) · Română

Pentru mesaje în română, adaugă `--lang ro` ca primă opțiune la `./Inventar.command` și `python3 Pregateste-fstab.py`.

## Primul pas pentru un calculator nou

Deschide `Inventar.command` dintr-un macOS funcțional pe calculatorul care urmează să pornească Golden. Lasă conectate discurile pe care le vei folosi la probă. Inventarul citește metadatele prin `diskutil`, cu permisiunile utilizatorului. Raportul obișnuit poate fi copiat în fișa de caz. Identificatorii de forma `diskNsM` sunt valabili pentru pornirea curentă.

Pe MacBookPro9,1, Golden 26B131 a afișat Setup Assistant după ce două reguli specifice volumelor interne au oprit automontarea NTFS și exFAT. Pe un alt calculator, un volum NTFS sau exFAT care apare în inventar reprezintă un candidat la diagnostic. Notează întâi dacă prima configurare pornește normal. Pentru același simptom caută în captură atât așteptarea discului RAM la Setup, cât și cererea de montare rămasă în FSKit. O bară de progres oprită singură oferă prea puține informații pentru a atribui cauza.

## Pregătirea profilului

[Ghidul de inventar](Inventar.ro.md) arată cum se selectează explicit partițiile. [Ghidul de previzualizare fstab](Previzualizare-fstab.md) arată cum se generează cu Python 3 o propunere pornind de la copia fișierului `private/etc/fstab` de pe volumul Data Golden al țintei. Inventarul și previzualizarea pot fi folosite înainte de prima pornire, inclusiv din Tahoe. Regulile conțin UUID-urile sistemelor de fișiere de pe calculatorul respectiv. Identificatorii partițiilor GPT, numele de disc și etichetele volumelor au alte roluri.

Pachetul se oprește la previzualizare. Pentru prima aplicare pe un model nou se pregătește un profil reversibil pentru copia Golden, cu identificarea țintei System/Data și conservarea configurației inițiale. Pachetul de activare destinat MacBookPro9,1 are propriile identificatoare și se folosește doar pe configurația pentru care a fost construit.

## Dovezi de păstrat

Completează [fișa calculatorului](Fisa-calculator.md) pentru fiecare combinație de hardware și build. Pe Hackintosh, notează placa de bază, controlerul de stocare, procesorul și GPU-ul reale, separat de SMBIOS. Înregistrează distinct prima fereastră Setup, desktopul, a doua pornire și accesul la date. Un profil local care conține UUID-uri rămâne în dosarul privat al calculatorului.

Un volum cu `ro,noauto` rămâne în afara automontării și după login. După confirmarea desktopului și a unei reporniri stabile, poți testa separat un singur volum printr-o cerere explicită de montare numai pentru citire. Starea `Open` din IORegistry, faptul că volumul a fost montat și citirea reușită a unui fișier sunt trei observații diferite.
