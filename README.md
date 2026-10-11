# NHL Game Score

En egen statistiksida för NHL som uppdaterar sig själv varje morgon. Den hämtar alla matcher direkt från NHL, räknar fram Game Score+ för varje spelare och match, ritar ett matchkort per match och lägger ut allt på en webbsida.

Allt körs gratis på GitHub. Du behöver inte ha datorn igång.

## Det här får du

- **Startsidan:** säsongens stjärnor, alla spelare, lag, målvakter, matcher, och säsongens bästa och sämsta insatser.
- **Matchkort:** ett per match, som bild att ladda ner och lägga upp (1080 × 1350).
- **Excel-fil** med all statistik, en flik per tabell.
- **Två formler att växla mellan:** vår Game Score+ och originalet.

## Kom igång (en gång, ungefär 10 minuter)

1. **Skapa ett konto** på [github.com](https://github.com). Det är gratis.
2. **Skapa ett projekt.** Klicka på **+** uppe till höger och välj **New repository**.
   - Ge det ett namn, till exempel `nhl-statistik`.
   - Välj **Public**.
   - Klicka på **Create repository**.
3. **Ladda upp filerna.** Klicka på länken **uploading an existing file**.
   - Packa upp zip-filen och dra in allt som ligger i mappen, inklusive mappen `webb`.
   - Klicka på **Commit changes**.
4. **Lägg till schemat.** Mappar som börjar med punkt är ofta dolda och följer inte med när man drar in filer. Gör så här:
   1. Klicka på **Add file** och sedan **Create new file**.
   2. Skriv exakt `.github/workflows/uppdatera.yml` som filnamn. Snedstrecken skapar mapparna.
   3. Öppna filen `uppdatera.yml` från paketet, kopiera allt och klistra in.
   4. Klicka på **Commit changes**.

   Syns redan mappen `.github` i projektet kan du hoppa över det här steget.
5. **Slå på webbsidan.** Gå till **Settings** och sedan **Pages**. Under **Source**, välj **GitHub Actions**.
6. **Starta första körningen.**
   1. Gå till fliken **Actions**. Klicka på den gröna knappen om GitHub frågar om du vill slå på arbetsflöden.
   2. Välj **Uppdatera statistik**, klicka på **Run workflow** och sedan på den gröna **Run workflow**.

   Första gången tar det 30–45 minuter, eftersom hela säsongen hämtas. Sedan tar det några minuter per dag.
7. **Klart.** Sidan finns på `https://DITT-ANVÄNDARNAMN.github.io/nhl-statistik/`. Under **Settings** och **Pages** står den exakta adressen.

Därefter uppdateras allt automatiskt varje morgon vid nio, svensk tid.

## Ditt namn på korten

Öppna `config.json` i projektet, klicka på pennan och byt `Ditt namn` mot det du vill ska stå på korten och sidan, till exempel ditt konto på X. Spara med **Commit changes**. Ändringen syns efter nästa körning.

I samma fil styr `dagar_med_bilder` hur många dagar bakåt det skapas nedladdningsbara bilder (standard 21).

## Game Score+

Game Score+ är vår vidareutveckling av Dom Luszczyszyns Game Score från 2016. Vikterna för mål, assist, blockeringar, utvisningar och tekningar är desamma. Två delar mäter i stället chansernas kvalitet:

| Del | Original | Game Score+ |
|---|---|---|
| Egna skott | 0.075 per skott på mål | 1.0 × ixG (spelarens förväntade mål) |
| Spelet på isen vid 5 mot 5 | 0.05 × (skottförsök för − mot) | 1.0 × (xGF − xGA) |
| Målvakter | −0.75 per insläppt mål + 0.1 per räddning | 0.75 × GSAx (räddade mål över förväntan) |

Förväntade mål räknas med en egen modell, en logistisk regression. Den tränas om på säsongens alla skott vid varje körning och väger in avstånd, vinkel, skottyp, returer, rusher och numerärt läge. Därför kan äldre matchers Game Score+ ändras lite när fler skott kommer in.

## Filerna

| Fil | Vad den gör |
|---|---|
| `nhl_stats.py` | Hämtar matcherna från NHL och räknar all statistik. Kan också köras på egen dator och ger då en Excel-fil. |
| `bygg_sida.py` | Bygger webbsidan och matchkorten från statistiken. |
| `webb/` | Webbsidans utseende: startsidan, matchkortet och stilen. |
| `.github/workflows/uppdatera.yml` | Schemat som kör allt varje morgon. `uppdatera.yml` är en kopia att klistra in i steg 4. |
| `config.json` | Ditt namn och antal dagar med bilder. |
| `statistik/` | Skapas automatiskt. Tabellerna för spelare, målvakter, lag och matcher sparas här varje dag. |

## Bra att veta

- **Om en körning misslyckas** syns ett rött kryss under **Actions**. Klicka på körningen och se vilket steg som stoppade. NHL:s datatjänster är öppna men inte officiellt dokumenterade, och kan ändras. Kopiera felmeddelandet och fråga, så går det att rätta.
- **GitHub pausar schemat** i publika projekt efter 60 dagar utan aktivitet. Under säsongen sparas nya tabeller varje dag, vilket räknas som aktivitet. Efter sommaruppehållet kan du behöva slå på det igen: gå till **Actions**, välj **Uppdatera statistik** och klicka på **Enable workflow**.
- **Före säsongsstart** visar sidan förra säsongens statistik tills den nya har börjat.
- **Köra på egen dator:**
  ```
  pip install -r requirements.txt
  python nhl_stats.py
  python bygg_sida.py
  python -m http.server --directory site
  ```
  Öppna sedan http://localhost:8000 i webbläsaren.

Data: NHL. Formel: Game Score+, vidareutvecklad från Dom Luszczyszyns Game Score (Hockey Graphs, 2016).
