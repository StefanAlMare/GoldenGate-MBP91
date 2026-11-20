# Golden Gate A pe MacBookPro9,1

Construcția inițială a folosit HAO `6bd75aab112d1078acd8e75180eb510672461365` și macOS Golden `26B131`. Pentru etapele 2–4 s-au regăsit bonurile originale și modificările de profil păstrate în Git, la `0b3d86a`. Pentru etapele 5–13 s-au regăsit 24 de scripturi istorice, inclusiv variantele intermediare, și două patch-uri de text.

| Etapă | Ce consemnează bonul | Sursa de urmărit |
|---|---|---|
| 2 | HAO recunoaște ținta 9,1, încarcă profilul și îl acceptă în constructorul hardware. | `0b3d86a`, definiția țintei și profilului |
| 3 | Planificatorul acceptă operațiile și constructorul produce pachetul hardware. | `0b3d86a`, profilul de operații hardware |
| 4 | Se construiește EFI de bază și trece verificarea cu `ocvalidate`. | `0b3d86a`, integrarea EFI și OCLP |
| 5 | Sunt pregătite intrările Apple, componentele de sistem în spațiul utilizator și kernelul. | `constructor/HAO-mbp91-step5.py` |
| 6 | Sunt pregătite sursele din sistemul donator și instrumentele pentru kernel și extracție. | `constructor/HAO-mbp91-step6.py` |
| 7 | Se construiesc runtime-ul pentru țintă și extensia de kernel anterioară marcării finale. Testele pe gazdă trec. | `constructor/HAO-mbp91-step7*.py` |
| 8 | Se pregătește pachetul minim pentru pornire. Bonul marchează pachetul runtime complet ca încă nefinalizat. | `constructor/HAO-mbp91-step8*.py` și `step8-packager.patch` |
| 9 | Se pregătesc componentele Metal și resursa grafică pentru ecranul de întâmpinare. | `constructor/HAO-mbp91-step9*.py` și `step9-hello-builder.patch` |
| 10 | Se pregătesc bibliotecile de compatibilitate pentru afișare, Wi-Fi, Metal și alte componente folosite la asamblare. | `constructor/HAO-mbp91-step10.py` |
| 11 | Sunt pregătite KDK și driverele. Se construiesc colecțiile de kernel și reparațiile. | `constructor/HAO-mbp91-step11*.py` |
| 12 | Se asamblează imaginea A și EFI finală. Imaginea brută, înainte de extinderea APFS, are SHA-256 `52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35`. | `constructor/HAO-mbp91-step12*.py`; bon separat al asamblorului |
| 13 | Bonul confirmă scrierea și recitirea imaginii, relocarea GPT, extinderea APFS, verificarea EFI și ejectarea. Verificarea pornirii fizice figurează separat în dosarul de probe. | `constructor/HAO-mbp91-step13.py` |

[BONURI.tsv](BONURI.tsv) conține amprentele celor 15 fișe din arhiva tehnică, alături de cele ale bonurilor originale disponibile pentru comparație. Arhiva privată de referință `GoldenGate-Arhiva-Tehnica-MBP91.zip` are SHA-256 `9ae5180f8e9d02190e32c3093f57963aae778cd446f7cd0ea61ce8f419903603`. S-au verificat cele 43 de intrări acoperite de manifestul intern. A 44-a intrare este manifestul.

[SURSE.tsv](SURSE.tsv) identifică fiecare sursă prin două amprente SHA-256, a fișierului de origine și a copiei arhivate. Cele 25 de fișiere din [probe-16-19](probe-16-19) completează construcția cu sursele probelor ulterioare de jurnal, DiskImages și automontare. Reviziile 18 și 19 se păstrează separat pentru a putea urmări schimbarea de la proba NTFS la proba pentru ambele sisteme de fișiere.

Fișierele arhivate au rol documentar. În sursele care identificau unitățile fizice, copiile folosesc UUID-uri și identificatori de test. La etapa 13 destinația fizică a scrierii este marcată `diskNECONFIGURAT`. Cele două amprente diferă acolo unde s-au înlocuit valori locale. Intrările Apple, jurnalele integrale, imaginile de disc și capturile rămân în arhiva privată de origine.
