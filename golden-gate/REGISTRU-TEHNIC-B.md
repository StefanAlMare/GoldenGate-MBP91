# Golden B · Registrul intervențiilor și al probelor

**MacBookPro9,1 · Golden Gate 27.2.1 (26B131) · 19–20 noiembrie 2026.** [Istoricul A și B](ISTORIC-A-B.md) descrie construcția, SSD-ul și cele trei porniri. Aici sunt identificate fișierele instalate pe B, experimentele retrase și dovezile pentru fiecare decizie. SHA-256 din coloanele „raport” identifică raportul text original. Observațiile pe ecran sunt atribuite separat.

Autorul principal al HAO este **lythka**. **StefanAlMare ([@StefanAlMare](https://github.com/StefanAlMare))** a condus portarea locală și probele fizice. Implementarea instrumentelor și a adaptărilor locale a fost realizată cu **Codex (OpenAI)**.

## Intrările constructorului

| Reper | Conținut și identificare |
|---|---|
| Constructor B | Commitul local `2a00ef190a10a2a51e069fbeb3a2f691ba387873` reunește profilul de 36 de operații, lista de 10 intrări pentru cache și rețeta desktop revizia 2. Operațiile aplicate ulterior pe SSD au bonuri separate. |
| Profil hardware | Eliminarea celor două suprascrieri ImageIO și CMPhoto este în `21fae1f97bd796af44cfa707e916d32781968cff`. Pachetul rezultat are SHA-256 `f3c22a45c1b6350fc743b6d4df4af1b5fadbac3da195ea683eedf9d4692e83a4`. |
| Cache și kit | Lista B are SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`. Manifestul kitului verificat cu 36 077 de intrări are SHA-256 `fb07b7b93fa70396e5ed322d7309a7fb1b5c48f0ef6a8a859bc1b5c46ae41a0a`. |
| Runtime și EFI | Binarul x86_64 `libhao.dylib` construit din `1547dcb4` are SHA-256 `11760e88422c301f2d99f32581902c4e891e7819110aab0565e65e14f34a1a45`. Partiția EFI brută din imaginea B are SHA-256 `42409d2a85dc78786278e685cbca54848304943198dea74833a6df63ce3e62ab`. |

## Finder și IconServices

| Experiment | Rezultat și decizie | SHA-256 raport |
|---|---|---|
| Inventarul contului B | Din 668 de nume de fișiere din manifestul de referință, 16 corespundeau unor fișiere nenule. Indexul utilizatorului lipsea. Inventarul verifica numele și existența. | `666bd8b0ca94b7828cc99032dd21ce788752827855a4f96b8859d16ff1775221` |
| Import temporar al cache-ului din A | În A, indexul de 720 896 B avea 456 de înregistrări rezolvabile, dar generarea imaginilor continua să eșueze. Importul pe B a lăsat 97 de erori Foundation 4097 pe probă, atât înainte, cât și după. S-a verificat revenirea. | `b12f2fe0fbbc2ed954d8f59c3adbcf2b21bbebbe6d207a3c2a7da560ae9fb7f0` |
| Client Intel și client cu HAO | În aceleași cereri de pictogramă, atât clientul Ruby Intel fără libhao, cât și osascript cu libhao au reprodus eroarea 4097. Serviciul XPC de control a răspuns corect clienților x86_64 și ARM prin HAO. | `5c2a2eee2914cfdf3d95043341462bb1ff910a8f9f51b5ad1bc6ba315ec475c7` · `1e7271b473ffc767ad946c47d1cac86d447cc7911908c151dab7c0dc34a86ac1` |
| Agentul Apple Intel din Tahoe 25G422 în sesiune | Cele patru cereri pentru dosarul Aplicații au trecut de la 73 de erori fiecare la zero. Au răspuns și cererile pentru Finder, Configurări sistem și Monitor activitate. Finder deja blocat și-a revenit după relansare. Proba a fost repetată după repornirea cu reparația de ferestre. | `705b6be514163fd14f3398eb976199653b82313f9931a4d1ca01ca46fdf89675` · `e6141edd14d1c20156b60aaebf18aae665e4135e394db088aa5ef5dcb44e3e97` |
| Agentul pe snapshot | Bonul `hao-20261120-144841` consemnează o singură scriere. După repornire, operatorul a confirmat Finder receptiv la autentificare. | `c35bc125328b64be24fb628d97dbe7460e8c0b0b7a8531e835759dc8acd230ca` |

| Fișier sau intrare | SHA-256 |
|---|---|
| Indexul recuperat pe A, folosit pentru comparație | `fe6be8430620640f462def2224a9738b8965be2229dfe05179bad69d22ca68c0` |
| Agentul Golden cu înveliș HAO, înainte de înlocuire | `cf1e92d68dcc75d290ad6ea693d04fc0d7a96d5b4be8d1ded6228751fa55bf82` |
| Agentul Apple cu felie Intel nativă, semnătură verificată | `0c34b609f914b0f1e1e263268528e04715ce59d4de34770cba3af1d40d752de8` |
| Intrarea desktop revizia 1, agent și unitate SkyLight de 155 B | `725eac8c823cf3c910d34c4350b56310ed65d7aeca2410c983e3d4873b85c0a6` |
| Intrarea desktop revizia 2, agent și unitate cumulativă de 255 B | `59eb5b9895a988a4ac472be21e511d900a47219961f782a09c01e7132447b9fd` |

## Dock, Opțiune și Foundation

| Intervenție | Verificare și domeniu | SHA-256 raport |
|---|---|---|
| Dock, diagnostic | Mărirea și ascunderea erau configurate. Preferințele au fost confirmate la 48 și 128 pt. În proba ARM, șase citiri considerau butonul apăsat când era liber. Cu descrierea returnării pe un octet, erorile au trecut la zero și au revenit la șase după retragere. | `46d6899efe48d5ab2d662c597cb9eafad036b251fa5a6f6a1f3c6e103fe1bf78` · `742349398396b74b79134e9b4e748dbf7ee3492c5332a107566d0efa54d0ab9c` |
| Dock, aplicare | S-a simulat aplicarea, apoi bonul `hao-20261120-135221` a consemnat unitatea pentru `CGSInputButtonState` și `SLSInputButtonState`. Etichetele, mărirea și reapariția la margine au fost confirmate după repornire. | `105bc4a4d1668b5a6d19be1470e4edf81847f95e3695ede0e07c7c0b968dd339` · `5799c94a8d154f9f7bb8f60529cd20d447b622c240c630561c96a36e7805027d` |
| Tragerea ferestrelor | La citirea tastei Opțiune libere, proba ARM a dat șase retururi eronate. Unitatea cumulativă a corectat `CGSInputModifierKeyState` și aliasul `SLSInputModifierKeyState`, păstrând cele două descrieri Dock. Bonul `hao-20261120-141809` consemnează înlocuirea. Confirmare fizică după repornire pentru tragerea obișnuită. | `29e0f8b4c9a4f47c7f1c9bf4f78ee94a0493e8fc97b0f0fea41b5cee839775d9` |
| Baterie, diagnostic | Două căderi PowerPreferences au arătat aceeași oprire la `PowerPreferences+0x54e14`, cu Charts în stivă. Pentru `DateComponents(hour: 0)`, Intel producea o dată, iar procesul ARM prin HAO întorcea `nil`. | `46d6899efe48d5ab2d662c597cb9eafad036b251fa5a6f6a1f3c6e103fe1bf78` · `af99285d9ac2b0b62beccddca86e56282416ad6925cb2609ac58efc764f61f30` |
| Baterie, aplicare | Corecția Foundation pentru argumentele inițializatorului Swift a fost aplicată pe snapshot, bon `hao-20261120-155230`. După repornire s-au verificat fișierul, rezultatul ARM și continuitatea procesului timp de 30 s. Filtrul de istoric din acea primă verificare a eșuat la caractere UTF-8. | `c0965f6634bfb2cefb110f1298a281c993bad9e804b743aa4c43b73de2583da2` · `60e3c17684afb419bea117f8fde4f2cf3bc0912bc8dc936b71d7f5a7f0ef7b56` |

| Unitate HAO instalată | SHA-256 al fișierului |
|---|---|
| SkyLight pentru Dock, 155 B | `a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f` |
| SkyLight pentru Dock și Opțiune, 255 B | `cd2a77b0e61af60abd4c23e860809aad0af4837dc81886a600831379c2546b3f` |
| Foundation pentru Calendar, 408 B | `1a1220644804cd8b9ea448d9a55421dcd3742b8542862fc54c48d2c11541d48d` |

## Graficele bateriei, pictogramele și Centrul de control

| Probă | Ce a măsurat | SHA-256 raport |
|---|---|---|
| Istoricul bateriei | Cu filtrul corectat s-au citit în jurnal 96 de intervale pentru nivel și 24 pentru ecran activ. Cele patru avertismente priveau chei ale răspunsului fără configurație corespunzătoare în cerere. | `68cc27ffc9a5aceebfb4434ce6a8e87b7630854a2f6b57c519ab3d9e7240924d` |
| Fișierul PowerLog | La 24 h s-au găsit 31 de niveluri valide de 95–100% și 10 durate de 300–3 600 s. La 10 zile s-au găsit două durate pozitive pentru ecran activ și zero valori pozitive pentru consum. | `83873cd2c0c377de1bb5574874d8d65e6e2a6d3e4f02fc5481b409295f58ccee` |
| Citirea barei în utilizare | Ambele ecrane erau pe GT 650M. Au fost deschise Wi-Fi și Bluetooth. În cele 25 s de probă, filtrul nu a găsit erori grafice relevante sau mesaje ale serviciului de compilare. În capturi anterioare existau erori grafice. | `5e589929d4bf67affd12bd7b03d3f3a6d73ff03c251950a4c30d005260108e6b` · `2c05f076a60bb4e4a696d617a737763fd3958f21014bbfe44723c214cb84a4c5` |
| Simbolurile AppKit și afișarea lor | Un proces Intel fără libhao și unul cu libhao au produs aceleași măști pentru Wi-Fi, Bluetooth și difuzor. Într-un element AppKit temporar din bara Aqua s-au văzut toate cele patru faze, inclusiv Wi-Fi negru pe alb. În bara nativă difuzorul se vedea, iar locurile Wi-Fi/Bluetooth erau goale și răspundeau la clic. Opacizarea barei nu a refăcut simbolurile. | `6931375e10908958edd76da442e713caea4f8239b3b5f15d7ab6e2622a3fcc08` · `8a6b4bcb306e289c575a4c080400f2cc1e5e19d070608780befb77f83ea79d53` |
| Butonul Centrului de control | Două rapoarte distincte confirmă SIGSEGV în `swift_setAtWritableKeyPath + 28`. În ambele cazuri procesul ControlCenter s-a relansat, iar PowerPreferences și WindowServer au continuat. Din cele 495 de cadre ale fiecărei stive, niciunul nu conține adresa de retur urmărită pentru corecția upstream `256dd30`. Efectul acelei corecții pe acest Mac rămâne nedemonstrat. | `46bae5ca8e286e928bbcbd8ef48d581ef1366301861c3c7c29e999b34f5fe719` · `9b5e3d642ae950daa3aacf568f31c0f4df00c86590d83b21ac02a993bf6a6c1a` |

Fotografiile și observația operatorului adaugă două lucruri pe care rapoartele de mai sus nu le măsoară. Graficul ecranului activ pe 24 de ore a afișat uneori zece bare în două grupuri, apoi și-a schimbat aspectul la alternarea Finder–Configurări sistem. Fenomenul s-a repetat și cu afișajul intern pe Intel HD 4000. În bara de meniu, simbolul bateriei era pal și fără indicația obișnuită, deși panoul arăta „Încărcată complet”. Reparația Foundation rămâne validată pentru deschiderea extensiei.

## NTFS și exFAT la 20 noiembrie

| Succesiunea pe SSD-ul B | Rezultat | SHA-256 raport |
|---|---|---|
| Cererea inițială pentru ambele volume | Proba s-a oprit prin expirare după identificarea NTFS. Inventarul ulterior a găsit ambele volume nemontate. | `64b455404e0717e67acafa256c9c9736673dc1fd8b499c74bd59612c9904837e` · `82251974b7b1210f310eb017e896b70fc951ba7d8357b1b6e2fd035807c69273` |
| Componente înainte de o nouă încercare | Pentru NTFS a fost identificat UserFS. Pentru exFAT au fost identificate UserFS, kext în declarație și extensia FSKit executabilă. Ambele biblioteci LiveFiles erau prezente în cache-ul dyld Intel. Era activă câte o regulă `ro,noauto` pentru fiecare volum. | `ca1a1e2a9afe20ebe7bfc9405d93984d8ee626bbf5722e9049415644a9d87506` |
| Cerere separată exFAT | Cererea de montare numai pentru citire a expirat după 75 s. | `9cd46fe3e31fa4fe079471349541597726c6886c0590fcd6291e37018ed21b57` |
| După trecerea la `ro,auto` și repornire | S-a ajuns la login. Inventarul a verificat ambele reguli și a găsit ambele volume nemontate. | `aa5014ed53ba809c80d190026a4c4101cfe051e305bd323509b7b3a8b7b6e6ea` |
| Jurnalul acelei porniri | Regulile fuseseră modificate cu 109 s înainte de pornire. Disk Arbitration a selectat sondarea FSKit pentru exFAT. Extensia s-a lansat, a recunoscut resurse și a încheiat o verificare. Mesajul serviciului privind configurarea clientului și evenimentele cu identificator mascat nu demonstrează montarea unui volum anume. | `fee57b8ef993dcc2b8fd0fcd6f5bcf13b799e10e166206b2e720a25a502d6e25` |

Pentru B rămân deschise citirea efectivă a unui fișier pe fiecare format, afișarea pictogramelor native Wi-Fi/Bluetooth și Vreme, indicatorul aplicațiilor active din Dock, graficele bateriei și pierderea imaginii la deconectarea HDMI din hubul Thunderbolt. Adaptorul direct mini DisplayPort–HDMI a funcționat la reconectare. Operatorul a raportat artefacte în transparențele din Găsire cu afișajele pe NVIDIA.
