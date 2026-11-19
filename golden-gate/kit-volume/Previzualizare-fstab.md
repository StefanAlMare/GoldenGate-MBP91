# Pregătirea profilului pentru un calculator

[English](Fstab-preview.md) · Română · [Kit pentru volume](Citeste.md)

Din macOS funcțional, pornește inventarul pe calculatorul care va rula Golden, cu discurile relevante conectate. Identificatorii de forma `disk…` sunt valabili în pornirea curentă. Alege explicit partițiile NTFS sau exFAT afectate.

```sh
./Inventar.command --lang ro
```

Exemplul de mai jos folosește două identificatoare fictive. Înlocuiește-le cu cele din inventarul tău. Rulează comenzile în directorul extras. Numele de ieșire trebuie să fie libere. UUID-urile din plan rămân în profilul privat al calculatorului.

```sh
(set -C; ./Inventar.command --lang ro --plan disk7s3 disk7s6 > plan-local.txt)
```

Constructorul citește fișierul `private/etc/fstab` de pe volumul **Data Golden destinat probei**. Dacă există, salvează o copie locală cu numele `fstab-original.txt`. Apoi generează o previzualizare cu Python 3.

```sh
python3 Pregateste-fstab.py --lang ro --plan plan-local.txt --base fstab-original.txt
```

Dacă ai verificat că fișierul lipsește pe țintă, folosește `--empty` în loc de `--base fstab-original.txt`. Pentru a păstra rezultatul într-un fișier nou de lucru:

```sh
(set -C; python3 Pregateste-fstab.py --lang ro --plan plan-local.txt --base fstab-original.txt > fstab-propus.txt)
```

Verifică mesajele, codul de ieșire și diferența față de original. Un fișier nou poate rămâne gol dacă validarea eșuează. O regulă identică existentă este păstrată. O regulă concurentă, repetată ori o intrare `LABEL=` sau `/dev/…` care ar putea desemna același volum necesită revizuire manuală. Programul afișează doar rezultatul după verificarea întregului plan. Redirecționarea prin shell către un fișier existent poate goli fișierul înainte ca programul să pornească; folosește întotdeauna un nume nou și protecția `set -C`.

Integrarea aparține etapei de asamblare a copiei Golden și se verifică separat pe fiecare calculator. Pentru MBP9,1 există deja pachetul de activare/retragere verificat. Un profil obținut pentru alt calculator necesită verificarea separată a discului Golden țintă, a originalului și a restaurării înainte de aplicare.
