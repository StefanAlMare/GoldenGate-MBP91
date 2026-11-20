# Golden Gate pe MacBookPro9,1

[English](README.md) · **Română**

[Istoricul complet al etapelor A și B](golden-gate/ISTORIC-A-B.md) urmărește compilarea, crearea imaginii și a USB-ului, cele trei probe de pornire, reparațiile verificate pe laptop și problemele rămase.

Pe 19 noiembrie 2026, **StefanAlMare** a ajuns la Setup Assistant și a început configurarea Golden Gate 27.2.1 (26B131) pe un MacBook Pro de 15″, Mid 2012. Mac-ul a pornit de pe un SSD USB extern. Configurarea a devenit accesibilă după adăugarea a două reguli `ro,noauto`, una pentru volumul intern NTFS și una pentru volumul intern exFAT.

StefanAlMare a ajuns ulterior la desktop și s-a autentificat din nou după repornire. Proba Metal a selectat explicit NVIDIA GeForce GT 650M și a citit corect toți cei 16 pixeli ai unei suprafețe de randare. În inventarul făcut înainte de probă, ecranul intern era pe Intel HD 4000. [Fișa stadiului 1](golden-gate/STADIUL-1.md) identifică imaginea, EFI-ul și runtime-ul folosite pe Mac și compară cele trei probe de pornire. [Kitul de inventar](golden-gate/kit-volume/Citeste.md) permite verificarea volumelor și previzualizarea regulilor fstab pentru fiecare calculator.

## Credite

[lythka](https://github.com/lythka) este autorul principal al HAO. [Prezentarea în română a proiectului original](README.upstream.ro.md) descrie rezultatele obținute pe MacBookPro9,2. Contributorii și licențele componentelor sunt consemnate în [documentul de atribuire](NOTICE.md).

**Ștefan Ilmare (@StefanAlMare)** a condus adaptarea pentru MacBookPro9,1, a efectuat probele pe hardware și a confirmat rezultatele pe ecran. **Codex (OpenAI)** a implementat adaptările locale, instrumentele de construcție și diagnostic și a documentat rezultatele.
