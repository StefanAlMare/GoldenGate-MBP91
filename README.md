# Golden Gate pe MacBookPro9,1

**Pe 19 noiembrie 2026 am ajuns la desktopul macOS 27.2.1 Golden Gate (26B131), pornind de pe un SSD USB extern, pe un MacBook Pro de 15″ din 2012.** Am repornit laptopul și ne-am autentificat din nou. Pe 20 noiembrie am închis prima etapă cu două imagini documentate. A este prima care a pornit. B este exemplarul pe care am verificat și reparat folosirea zilnică a desktopului.

## De unde am plecat

Am descoperit proiectul HAO al lui **lythka**, care adusese Golden Gate pe MacBookPro9,2, modelul de 13″ din 2012. Aveam un laptop din aceeași generație, cu procesor din aceeași familie Ivy Bridge și cu grafică Intel HD 4000. Modelul nostru de 15″, **MacBookPro9,1**, are în plus o placă NVIDIA GeForce GT 650M și comutatorul grafic GMUX. Am pornit de la codul autorului ca să aflăm dacă putem porni sistemul pe acest hardware și folosi ambele plăci grafice. [Proiectul HAO](https://github.com/lythka/hao-patcher) · [Documentația originală în română](README.upstream.ro.md)

## Imaginea A — de la codul HAO la USB

1. **Am definit profilul laptopului.** Am pornit de la constructorul HAO `6bd75aab`. Am adaptat profilul OpenCore pentru GMUX și selecția driverelor Intel Ivy Bridge și NVIDIA Kepler din OpenCore Legacy Patcher. Am păstrat driverul Intel pentru ecranul intern și am inclus driverele NVIDIA necesare GT 650M. EFI-ul de bază a trecut verificarea cu `ocvalidate`.
2. **Am compilat pe iMac.** Am combinat sistemul Apple Golden `26B131` cu componentele Intel din Tahoe `25G342`. Am compilat local runtime-ul HAO `1547dcb4` și extensia HaoExec. La împachetare am verificat 963 de executabile Apple, inclusiv `launchd` și `xpcproxy`, necesare încă de la pornire.
3. **Am asamblat imaginea.** Am pregătit bibliotecile Metal, animația „Hello” din prima configurare, driverele, colecțiile kernel, volumele APFS și Preboot. Profilul hardware al imaginii A cuprindea 38 de operații. Imaginea completă avea 80 GiB.
4. **Am scris și verificat SSD-ul.** După transfer am recitit integral cei 80 GiB. Amprenta SHA-256 de pe USB a coincis cu aceea a imaginii de pe iMac. Am extins apoi containerul APFS la capacitatea SSD-ului și am verificat din nou partiția EFI. [Sursele și verificările etapelor 2–13](golden-gate/etape-a/INDEX.md) · [Sursele constructorului A](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe)

## Cum am ajuns la prima configurare

| Pornire pe 9,1 | Ce am observat |
|---|---|
| Cu volumele interne disponibile pentru automontare | Bara de progres s-a oprit în jur de 60%. Discul RAM de 512 MiB folosit de prima configurare a rămas fără partiții. |
| Cu NTFS exclus de la automontare | exFAT a rămas disponibil. Discul RAM a avut același comportament, iar Setup Assistant nu a apărut. |
| Cu câte o regulă `ro,noauto` pentru NTFS și exFAT | A apărut Setup Assistant. Am parcurs configurarea, am ajuns la desktop și ne-am autentificat din nou după repornire. |

În timpul blocajului, DiskImages aștepta Disk Arbitration, iar stivele serviciilor arătau o cerere de montare prin LiveFS și FSKit. Capturile nu identifică partiția respectivei cereri. Pe acest laptop, rezultatul reproductibil a fost prima configurare cu ambele volume excluse.

La desktop am confirmat Wi-Fi, Bluetooth, sunetul, USB-ul, tastatura, trackpadul și tastele de luminozitate și volum. Ecranul intern a fost identificat pe Intel HD 4000. Separat, o probă Metal a selectat explicit GT 650M, a desenat o suprafață de 4 × 4 pixeli și a recitit corect toți cei 16 pixeli. [Cele trei porniri și proba Metal](golden-gate/STADIUL-1.md)

## Imaginea B — ce am schimbat și reparat

Am păstrat același sistem și același runtime. Pentru a investiga pictogramele și Finder, am scos din profil două suprascrieri Kepler ale componentelor de imagine ImageIO și CMPhoto. Profilul a trecut de la 38 la 36 de operații, iar lista folosită la pregătirea cache-ului, de la 12 la 10 intrări. Driverele Intel și NVIDIA au rămas prezente. Reparațiile de mai jos au fost aplicate ulterior pe SSD-ul B și verificate pe laptop după repornire. [Comparația tehnică A/B](https://github.com/StefanAlMare/GoldenGate-MBP91/blob/6ba34ef2f16e9442783ee9fbb724366673465670/docs/mbp91-kepler-imaging-test.ro.md)

| Problemă | Intervenție | Rezultat pe MacBookPro9,1 |
|---|---|---|
| Finder se bloca, iar pictogramele aplicațiilor lipseau. | După testarea cache-ului și a clienților IconServices, am instalat pe snapshot agentul Apple `iconservicesagent` cu cod Intel nativ din Tahoe `25G422`. | Cele patru cereri pentru pictograma dosarului Aplicații au trecut de la câte 73 de erori la zero. După repornire, Finder a funcționat de la autentificare. |
| Dock-ul nu reapărea corect, iar mărirea și etichetele pictogramelor erau afectate. | Am corectat în SkyLight modul în care HAO citea starea butonului mouse-ului. | Cele șase indicații false de apăsare au dispărut. După repornire au funcționat reapariția Dock-ului, mărirea și etichetele. |
| Tragerea unei ferestre declanșa aranjarea în mozaic fără să fie cerută. | Am completat aceeași corecție SkyLight cu citirea stării tastei Opțiune. | După instalare și repornire, ferestrele au putut fi trase normal. |
| Configurări sistem → Baterie se închidea. | Am corectat în Foundation apelul Swift `DateComponents` folosit de PowerPreferences. | Panoul s-a deschis și a permis alegerea între 24 de ore și 10 zile. Afișarea graficelor a rămas parțială. |

[Registrul intervențiilor, al experimentelor retrase și al probelor pe B](golden-gate/REGISTRU-TEHNIC-B.md)

## Ce a rămas deschis la închiderea primei etape

- **Volumele NTFS și exFAT.** Pe B, cererile de montare pentru citire au expirat. MacBook-ul a ajuns la login și cu regulile `ro,auto`, dar ambele volume erau nemontate. Au fost identificate componentele Apple pentru ambele formate, iar extensia exFAT a recunoscut o resursă.
- **Bara de meniu, Centrul de control și Dock-ul.** Zonele Wi-Fi și Bluetooth răspund la clic, dar simbolurile sunt invizibile. Simbolul bateriei este incomplet. Deschiderea Centrului de control a produs două căderi cu aceeași stivă. Indicatorul de sub o aplicație din Dock poate dispărea în timp ce aplicația continuă să ruleze.
- **Graficele bateriei și Vreme.** Sistemul citește bateria, iar istoricul conține valori. Graficul de 24 de ore apare intermitent la schimbarea ferestrei active, atât cu ecranul pe Intel, cât și pe NVIDIA. Aplicația Vreme se închide la lansare, iar pictograma ei lipsește din bară.
- **Monitorul extern și randarea Metal.** Adaptorul direct mini DisplayPort–HDMI permite conectarea și reconectarea monitorului. Prin hubul Thunderbolt am obținut imagine cu monitorul conectat la pornire, iar scoaterea HDMI a lăsat ambele ecrane negre. Pe NVIDIA persistă unele artefacte în transparențe și pe contururi.

**Prima etapă s-a închis la 20 noiembrie 2026.** Reperul rămas este un MacBookPro9,1 care pornește de pe USB, ajunge la desktop și se poate autentifica după repornire, cu cele patru intervenții de mai sus probate pe B. [Istoricul cronologic A/B](golden-gate/ISTORIC-A-B.md)

## Credite

| Contribuitor | Rol |
|---|---|
| **lythka** | Autorul principal al proiectului HAO și al bazei pentru Golden Gate pe Intel. |
| **Ștefan Ilmare** ([@StefanAlMare](https://github.com/StefanAlMare)) | Inițiativa și coordonarea adaptării pentru 9,1, probele pe hardware și confirmarea rezultatelor pe ecran. |
| **Codex (OpenAI)** | Implementarea adaptărilor locale, a instrumentelor de construcție și diagnostic și documentarea rezultatelor. |

[Licențe și atribuire, inclusiv OpenCore Legacy Patcher](NOTICE.md) · [English overview](README.en.md)
