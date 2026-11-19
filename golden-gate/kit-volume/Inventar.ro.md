# Inventarul discurilor pentru Golden Gate

[English](Inventory.md) · Română · [Kit pentru volume](Citeste.md)

Pentru un raport în română, rulează `./Inventar.command --lang ro` din Terminal.

Din Finder, deschide Inventar.command pe calculatorul evaluat. Raportul se afișează în Terminal. Poți rula inventarul din Tahoe înainte de instalare sau din Golden după configurare. Identificatorii diskNsM sunt valabili doar în sesiunea curentă. Modelul raportat este SMBIOS-ul prezentat sistemului. Notează separat dacă este un Mac original sau Hackintosh.

Inventarul folosește comenzile și bibliotecile macOS. Citește metadatele discurilor, fără sudo. Raportul afișează modelul declarat, arhitectura, buildul, locația și starea partițiilor. O partiție „Microsoft Basic Data” cu sistem de fișiere neidentificat cere investigație separată. Candidatura unei partiții indică doar un tip de sistem de fișiere și o identitate verificabile. Cazul MBP9,1 justifică testarea acestei ipoteze când simptomele și jurnalele sunt similare.

Pentru a examina regulile pe calculatorul tău, deschide Terminal în folderul acestui utilitar. Folosește identificatorii afișați la inventarul propriu. Exemplu de sintaxă:

```sh
./Inventar.command --lang ro --plan disk0s3 disk0s6
```

Această comandă afișează reguli fstab pentru volumele selectate explicit și include UUID-urile lor private. Rezultatul este o previzualizare. Formatele acceptate pentru plan sunt NTFS și exFAT pe partiții de date identificate. EFI, sistemul pornit, suporturile APFS ale acestuia și identitățile ambigue sunt excluse. O partiție de date de pe același disc fizic cu Tahoe poate fi selectată separat. Planul este refuzat dacă inventarul vizibil conține un UUID duplicat, chiar și pe un disc virtual, pentru o partiție selectată.

Copierea raportului obișnuit este suficientă pentru discuția despre compatibilitate. Păstrează planul cu UUID-uri pentru lucrul local. Utilitarul nu instalează reguli. Dacă instalezi separat o politică noauto în Golden, volumele vizate vor lipsi de la automontare inclusiv după configurare pe durata aplicării regulii.
