# Slotline

NHL-statistik som uppdaterar sig själv varje morgon. Slotline hämtar alla matcher direkt från NHL och räknar fram Game Score+ för varje spelare och match. Den räknar också ut vinstchansen inför kommande matcher och ritar ett matchkort per match. Allt läggs ut på en egen webbsida.

Allt körs gratis på GitHub. Du behöver inte ha datorn igång.

## Det här får du

- **Översikt:** nästa matchdag med vinstchans, senaste resultaten, säsongens stjärnor och tabelltoppen.
- **Vinstchans:** chansen att vinna för veckans matcher, en jämförelse av lagen och hur bra modellen har träffat hittills.
- **Matcher:** alla resultat med matchkort. Varje kort finns som bild att ladda ner och lägga upp (1080 × 1350).
- **Spelare, Tabell och Målvakter** med lagens loggor, filter och sortering.
- **Matchrapport** för varje match: alla mål med assist, lagens statistik och hela statistiken för alla spelare.
- **Spelarsidor** med all säsongsstatistik och match för match. Tryck på en spelare var som helst på sidan.
- **Tur & otur:** förväntade poäng visar vilka spelare som borde ha fler poäng än de har, och vilka som haft flyt.
- **Excel-fil** med all statistik, en flik per tabell.
- **Anpassad för mobil och dator:**
  - På mobil finns en menyrad med ikoner längst ner, och korten sveps i sidled.
  - På datorn ligger menyn överst och översikten har två kolumner.

## Kom igång (en gång, ungefär 10 minuter)

1. **Skapa ett konto** på [github.com](https://github.com). Det är gratis.
2. **Skapa ett projekt.** Klicka på **+** uppe till höger och välj **New repository**. Döp det till `slotline`, välj **Public** och klicka på **Create repository**.
3. **Ladda upp filerna.** Klicka på länken **uploading an existing file**. Dra in allt som ligger i mappen `slotline`, inklusive mappen `webb`. Klicka på **Commit changes**.
4. **Lägg till schemat.** Mappar som börjar med punkt följer ofta inte med när man drar in filer. Gör så här:
   1. Klicka på **Add file** och sedan **Create new file**.
   2. Skriv `.github/workflows/uppdatera.yml` som filnamn.
   3. Klistra in innehållet från filen `uppdatera.yml`.
   4. Klicka på **Commit changes**.
5. **Slå på webbsidan.** Gå till **Settings**, sedan **Pages**. Under **Source** väljer du **GitHub Actions**.
6. **Starta första körningen.** Gå till fliken **Actions** och välj **Slotline – uppdatera statistik**. Klicka på **Run workflow** och sedan på den gröna **Run workflow**. Första gången tar det 30–45 minuter, sedan några minuter per dag.
7. **Klart.** Sidan ligger på `https://DITT-ANVÄNDARNAMN.github.io/slotline/`.

Därefter uppdateras allt automatiskt varje morgon vid nio och varje kväll runt halv åtta, svensk tid.

## Uppdatera från en tidigare version

Har du redan satt upp projektet? Ladda upp de nya filerna på samma sätt som i steg 3 och skriv över de gamla. Lägg också in den nya `uppdatera.yml` som i steg 4: öppna `.github/workflows/uppdatera.yml`, klicka på pennan, ersätt allt och spara. Starta sedan en körning för hand (steg 6) så syns ändringarna direkt.

## Inställningar

Öppna `config.json` i projektet och klicka på pennan:

| Inställning | Vad den gör |
|---|---|
| `sajtnamn` | Namnet i sidhuvudet och på matchkorten (`Slotline`). |
| `namn` | Ditt namn eller konto, till exempel på X. Visas längst ner på sidan och på matchkorten. Lämna tomt (`""`) för att inte visa något. |
| `kontakt` | Länk dit man kan höra av sig, till exempel med frågor eller om något ska tas bort. Standard är projektets Issues-sida på GitHub. |
| `visa_loggor` | `true` visar lagens loggor från NHL. `false` visar i stället en prick i lagets färg bredvid förkortningen. |
| `dagar_med_bilder` | Hur många dagar bakåt det skapas nedladdningsbara bilder (standard 21). |

## Game Score+

Game Score+ är Slotlines vidareutveckling av Dom Luszczyszyns Game Score från 2016. Vikterna för mål, assist, blockeringar, utvisningar och tekningar är desamma. Det som skiljer är att chansernas kvalitet räknas, inte bara antalet skott:

| Del | Original | Game Score+ |
|---|---|---|
| Egna skott | 0.075 per skott på mål | 1.0 × ixG (spelarens förväntade mål) |
| Spelet på isen vid 5 mot 5 | 0.05 × (skottförsök för − mot) | 1.0 × (xGF − xGA) |
| Målvakter | −0.75 per insläppt mål + 0.1 per räddning | 0.75 × GSAx (räddade mål över förväntan) |

Förväntade mål räknas med en egen modell som tränas om på säsongens alla skott vid varje körning. Den väger in avstånd, vinkel, skottyp, returer, rusher och numerärt läge.

## Vinstchans

Modellen (`vinstchans.py`) räknar fram varje lags anfall och försvar ur säsongens matcher:

- **Anfall:** gjorda mål (utan mål i tom bur) och förväntade mål. Förväntade mål väger 70 %.
- **Försvar:** förväntade mål emot, alltså hur mycket chanser laget släpper till.
- **Målvakten** räknas för sig: insläppta mål delat med förväntade mål emot. Trolig startare är den som stått flest av lagets senaste tio matcher. Spelade han dagen innan räknas reserven som trolig. Kortet visar också chansen om reserven står.
- **Form och förra säsongen:** senare matcher väger mer än tidiga. Varje lag utgår från förra säsongens nivå, halvvägs mot ligasnittet, och målvakterna från förra säsongens räddningsprocent. Det gör att några matcher i början av säsongen inte ger orimliga siffror.
- **Matchen:** förväntade mål = eget anfall × motståndarens försvar / ligasnittet × motståndarmålvaktens kvot. Hemmalaget får 5 % fördel, och ett lag som spelade dagen innan får 3 % nackdel.
- **Chansen:** räknas med Poissonfördelning, där förlängning och straffar ingår.

Inställningarna är testade på säsongens spelade matcher, där varje prognos bara får se matcherna innan. Sidan visar också hur modellen hade tippat varje spelad match, så att man kan se hur bra den träffar.

## Förväntade poäng

Förväntade poäng = förväntade mål + förväntade assist.

- **Förväntade mål:** summan av xG för spelarens egna skott. Skott mot tom bur får ligans snitt för sådana skott.
- **Förväntade assist:** lagkamraternas xG när spelaren är på isen, gånger hur ofta en forward eller back får assist på ett sådant mål. Andelen räknas ur säsongen, för sig i powerplay. Spelarens egen andel vägs in men dras mot snittet, så att några få matcher inte avgör.

Har en spelare färre poäng än förväntat har han haft otur, och brukar komma ikapp.

## Filerna

| Fil | Vad den gör |
|---|---|
| `nhl_stats.py` | Hämtar matcherna och schemat från NHL och räknar all statistik. Kan också köras på egen dator och ger då en Excel-fil. |
| `vinstchans.py` | Modellen för vinstchans. |
| `bygg_sida.py` | Bygger webbsidan och matchkorten från statistiken. |
| `webb/` | Webbsidans utseende: startsidan, matchkortet och stilen. |
| `.github/workflows/uppdatera.yml` | Schemat som kör allt varje morgon. `uppdatera.yml` är en kopia att klistra in i steg 4. |
| `config.json` | Namn och inställningar. |
| `statistik/` | Skapas automatiskt. Tabellerna sparas här varje dag. |

## Bra att veta

- **Rättigheter:** Slotline är en oberoende fansida utan vinstsyfte och utan koppling till NHL, lagen eller Dom Luszczyszyn. Det står på sidan och på matchkorten. Lagnamn och loggor tillhör respektive lag och NHL. Loggorna hämtas direkt från NHL:s server och kan stängas av med `visa_loggor`. Håll sidan fri från annonser och betalning, och ta bort det du blir ombedd att ta bort.
- **Om en körning misslyckas** syns ett rött kryss under **Actions**. Klicka på körningen och se vilket steg som stoppade. NHL:s datatjänster är öppna men inte officiellt dokumenterade och kan ändras. Kopiera felmeddelandet och fråga, så går det att rätta.
- **GitHub pausar schemat** i publika projekt efter 60 dagar utan aktivitet. Under säsongen sparas nya tabeller varje dag, och det räknas som aktivitet. Efter sommaruppehållet kan du behöva slå på det igen under **Actions** med **Enable workflow**.
- **Köra på egen dator:**
  ```
  pip install -r requirements.txt
  python nhl_stats.py
  python bygg_sida.py
  python -m http.server --directory site
  ```
  Öppna sedan http://localhost:8000 i webbläsaren.

Data: NHL. Formel: Game Score+, vidareutvecklad från Dom Luszczyszyns Game Score (Hockey Graphs, 2016).
