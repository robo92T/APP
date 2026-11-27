# BID Dochádzka – porovnanie s oficiálnymi manuálmi Aktion (27.11.2026)

BID Dochádzka je samostatná aplikácia. Preberá procesné princípy, nie zdrojový
kód, grafiku ani právne záruky od dodávateľa Aktion. České nastavenia nemôžu
nahradiť slovenský Zákonník práce a schválené interné pravidlá BID.

## Overené zdroje

- Prehľad dochádzky eNext: https://navody.aktion.cz/cs/articles/13-prehled-dochazky
- Hromadný výkaz: https://help.aktion.cz/help/43b5d2ab686abe48900919661bc0a6b0
- Uzávierka dochádzky: https://help.aktion.cz/help/2258c7767eaae07c527c4f48302a9d21
- Plánovanie a schvaľovanie: https://www.aktion.sk/wp-content/uploads/2024/03/navod-aktion-cloud-zadosti.pdf
- Modely pracovného času: https://doc.aktion.cz/help/adaab937e41d576932ac8085d0678a88

## Doplnky v BID Dochádzka v8

| Oblasť | Stav | Poznámka |
| --- | --- | --- |
| Hromadný výkaz | Existoval vo v7 | Denný aj mesačný, filtrovanie, oddelenia, CSV/XLSX |
| Konfigurovateľné stĺpce výkazu | Nové | Výber zobrazených stĺpcov uložený v prehliadači |
| Uložený pohľad / filtre | Nové | Lokálne v prehliadači, nie naprieč zariadeniami |
| Kontrola zamestnancom | Nové | Záznam osoby, obdobia, času a autora; nemení pípnutia |
| Potvrdenie vedúcim | Nové | Len podriadení daného vedúceho, vlastné potvrdenie zakázané |
| Hromadná kontrola HR | Nové | Zamestnanci na jednom mieste s prehľadom potvrdení |
| Hromadná neprítomnosť | Nové | HR vyberie osoby, typ, termín, spustí simuláciu a potvrdí; atomický zápis |
| Preflight mzdovej uzávierky | Nové | Zoznam nepotvrdených osôb; voliteľný serverový blokovací režim |
| Opravy pípnutí s auditom | Už existovalo | Pôvodný riadok zachovaný ako zneplatnený/úprava s históriou |
| Rozpis zmien a cykly | Už existovalo | D–N–V–V a ďalšie |
| Kontrola prestávok a odpočinku | Už existovalo | Orientačné upozornenia, nie certifikované rozhodnutie |
| RFID terminály s offline frontou | Už existovalo | Len pri riadne nastavenom termináli |
| Mesačné PDF a exporty | Už existovalo | CSV, Excel, JSON, XML; mapovanie mzdového softvéru je doplnkové |

## Kľúčové rozdiely oproti Aktion – stále otvorené

1. **Dočasné časovo obmedzené zastupovanie vedúceho:** v BID je trvalý
   zástupca v organizačnom útvare, nie kalendár intervalov a e-mail
   notifikácie podľa platnosti zástupu.
2. **Schvaľovanie stornovania už schválenej žiadosti:** zatiaľ nie je
   samostatný dvojstupňový proces storna.
3. **Plnohodnotné schvaľovanie nadčasov, pracovná pohotovosť a mzdové
   zložky podľa konkrétneho predpisu/KZ:** zámerne nie automaticky.
4. **Kompletný zamykací workflow:** kontrola → potvrdenie → uzávierka
   je evidovaná a kontrolovaná; ešte nie všetky existujúce historické
   API operácie rešpektujú osobitný stav potvrdenia. Zákaz zápisov v
   globálne uzavretom mesiaci je čiastočne implementovaný.
5. **Konfigurovateľné modely pracovnej doby:** existujú rozpisy
   a šablóny, ale chýba plná robustná právna a výpočtová logika pre
   pružný čas, platené prestávky, vykazovanie náhradného voľna,
   automaticky generované pípnutia a výnimky podľa ZP.
6. **Prítomnosť podľa fyzických zón:** BID zobrazuje stav podľa
   posledného RFID záznamu. Nie je to prístupový systém s fyzickým
   sledovaním vstupov do zón.
7. **E-mailové notifikácie, doplňujúce poznámky a úpravy žiadostí
   vedúcim:** nie v rozsahu, ako opisuje manuál Aktion.
8. **Automatické hromadné mesačné PDF viacerých osôb naraz:** individuálne
   PDF existuje, výber viacerých PDF do jedného dokumentu zatiaľ nie.
9. **Zákonné upozornenia ZP:** upozornenia existujú, nie sú plne právne
   certifikované ani naviazané na všetky historické pracovné režimy.
10. **Trvalá databáza:** testovacia Render služba používa dočasnú SQLite.
   Nie je možné bezpečne odovzdať skutočné personálne údaje, kým
   nebude pripojené perzistentné PostgreSQL, zálohovanie a overená obnova.

## Odporúčaný postup pre BID

Najprv pripojiť a zálohovať PostgreSQL; potom doplniť
časovo obmedzené zástupy, schvaľované storná žiadostí, hromadné PDF
a špecifikáciu mzdových zložiek z kolektívnej zmluvy a mzdového programu.
Pred ostrou prevádzkou vykonať penetračný test, GDPR posúdenie a pilotnú
uzávierku súbežne so skutočným mzdovým účtovníctvom.
