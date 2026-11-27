# BID Dochádzka v9 – služobné cesty, stravné a nárok na stravovanie (27.11.2026)

## Legislatíva a platné sadzby

### Tuzemské cestovné náhrady (§ 5 zákona č. 283/2002 Z. z.)

Pri jednej pracovnej ceste sa stravné vyhodnotí **za každý kalendárny deň
samostatne** podľa skutočného trvania cesty v daný deň.

| Pásmo | 1.12.2025 – 30.11.2026 | Od 1.12.2026 |
|---|---:|---:|
| 5 – 12 hodín vrátane | 9,30 € | 9,80 € |
| Nad 12 – 18 hodín | 13,80 € | 14,60 € |
| Nad 18 hodín | 20,60 € | 21,70 € |

Podklady: oznámenia MPSVR č. 280/2025 Z. z. a 255/2026 Z. z.;
NIP https://www.ip.gov.sk/pracovnopravne-vztahy/pracovne-cesty/sumy-stravneho-od-1-decembra-2026.html

Pokiaľ sú poskytnuté **bezplatné jedlá**, odpočíta sa 25 % raňajky,
40 % obed, 35 % večera, vždy **z najvyššej dennej sadzby** (20,60 €
do 30.11.2026, 21,70 € od 1.12.2026). Výsledná denná suma sa
zaokrúhľuje na najbližší eurocent **nahor** a nikdy nesmie byť záporná.
Zamestnanec môže uviesť preukázateľný dôvod, pre ktorý bezplatné jedlo
nemohol bez vlastného zavinenia využiť; HR overí skutočnosti. Pri ceste
kratšej ako päť hodín je nárok spravidla nulový, no zákon pripúšťa
osobitné nenárokové plnenie zamestnávateľa, nie automatický výpočet.

### Stravovacia poukážka / finančný príspevok (§ 152 ZP)

Bežný zákonný nárok má zamestnanec za pracovnú zmenu, v ktorej
**vykonáva prácu viac ako 4 hodiny**; pri samotných 4 hodinách nevzniká.
Pri ceste spravidla nevzniká duplicitný bežný nárok, **výnimkou je
odpracovanie viac než 4 hodín na pravidelnom pracovisku**. Samotné
zaznamenané pípnutie nie je dôkazom toho, kde zamestnanec prácu vykonal.
Ak v deň pracovnej cesty existuje práca viac než 4 hodiny, systém
označí stav „preveriť pracovisko“ (automaticky neprizná poukážku).

| Obdobie | Minimálna hodnota poukážky | Minimálny príspevok zamestnávateľa |
|---|---:|---:|
| Od 1.12.2025 | 6,98 € | 3,84 € |
| Od 1.12.2026 | 7,35 € | 4,05 € |

Zákon umožňuje nad 11 hodín pracovnej zmeny poskytnúť druhé
stravovanie/príspevok podľa rozhodnutia zamestnávateľa, nejde o
automatický zákonný nárok. Interná smernica BID môže za splnených
podmienok rozšíriť oprávnené dni napríklad o ospravedlnené absencie.
Tieto výnimky **nie sú bez overenia zapnuté**.
Príspevok zo sociálneho fondu je individuálne nastavenie zamestnávateľa
a aktuálna v9 ho v automatickom výkaze nepripočítava.
Zdroj: https://static.slov-lex.sk/static/SK/ZZ/2001/311/20260901.print.html

### Náhrada súkromného vozidla (§ 7)

Od 1.1.2026 je referenčná základná náhrada pri osobnom aute
**0,313 €/km** podľa oznámenia č. 340/2025 Z. z. Okrem toho sa pri
splnení zákonných podmienok nahrádza spotreba pohonných látok.
V systéme musí HR uviesť počet km, spotrebu a cenu paliva,
prípadne ďalšie preukázané výdavky a preddavok.

Zdroj: https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2025/340/

## Implementované (testovacia verzia)

- Samostatný záznam pracovnej cesty s účelom, miestom, začiatkom,
  koncom, spôsobom dopravy, dokladovými výdavkami, preddavkom
- Automatický prepočet pásiem po kalendárnych dňoch vrátane
  zmeny sadzby od 1.12.2026 a krátenia za bezplatné jedlá
- Výpočet kilometrovnej náhrady za osobné auto, paliva,
  ostatných výdavkov, celkového nároku a doplatku po preddavku
- Výslovné schválenie / zrušenie cestovného príkazu s auditom
- Mesačný kontrolný prehľad **každého zamestnanca a dňa**,
  stravovací lístok a stravné pri schválenej pracovnej ceste
- CSV export pracovných ciest aj mesačného stravovania
- Označenie schválenej cesty v hromadnom výkaze
- Dve **výlučne fiktívne** ukážkové pracovné cesty pre Preview
- Doplnkové sledovanie zákona č. 283/2002, sadzieb a NIP
  v informačnom legislatívnom monitore (bez automatickej zmeny)

## Čo sa nesmie zamieňať za certifikovanú mzdovú agendu

- **Trvanie cesty nie je pracovný čas.** Pracovné saldo sa nezvyšuje
  o všetky hodiny cestovania. Prácu na ceste treba evidovať
  samostatne a pri chýbajúcom zázname doplniť HR kontrolou.
- **Zahraničné cesty:** časové pásma podľa prekročenia hraníc,
  krajiny, meny a sadzby podľa opatrenia č. 401/2012 Z. z.
  vyžadujú ďalší overený modul. Nie je implementovaný.
- **Výnimky a osobitné dohody:** mobilní zamestnanci, kombinácia
  niekoľkých ciest denne, prerušenia na súkromné účely,
  nevykonaná práca na ceste, iné sadzby podľa zákonnej dohody,
  prestávky, platené pracovné voľno a výnimočné stravovanie
  vyžadujú potvrdenie mzdárkou.
- **Automatický preddavok a rozpočtové schvaľovanie:** zatiaľ len
  evidencia a výsledné orientačné vyúčtovanie.
- **Doklady:** suma cestovného a ubytovania sa zadáva manuálne,
  neoveruje sa pravosť bločkov alebo účtovných dokladov.
- **Dátová bezpečnosť:** Preview je stále dočasná SQLite; ostré údaje
  nezadávať do pripojenia trvalej PostgreSQL s obnoviteľnými zálohami.

Pracovné a cestovné nároky schváľuje personálne/mzdové oddelenie.
Automatické výsledky sú pred ich potvrdením informatívne.
