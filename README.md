# 3D Target — Logo reveal (15 s)

Animazione di presentazione del nuovo logo 3D Target: minimale, cinematografica, in stile keynote.
1920×1080 e 1080×1920, 60 fps, 15,0 s, con colonna sonora originale sincronizzata.

## Struttura

| Percorso | Contenuto |
|---|---|
| `animation/3dtarget-logo-animation.html` | **File HTML autonomo**: SVG + Canvas, timeline scrubbabile, Play/Pausa, Replay, 16:9 / 9:16, tagline opzionale. Nessuna dipendenza esterna. |
| `render/render.mjs` | Render frame-by-frame (Playwright + ffmpeg) → MP4 H.264, CRF 14, BT.709. |
| `render/verify.mjs` | Confronto pixel per pixel del frame finale con il PNG originale (variante B). |
| `render/mux-audio.mjs` | Inserisce/sostituisce la colonna sonora negli MP4 esistenti senza ricodificare il video. |
| `audio/sound_design.py` | Sintesi della colonna sonora (musica + sound design) sui timestamp della timeline. |
| `audio/` | Master WAV 48 kHz/24 bit, stem `music`/`sfx`, AAC/Opus, report di loudness e grafico di sync. |
| `tools/trace_logo.py` | Vettorializzazione dei PNG ufficiali (potrace) → SVG + dati per l'animazione. |
| `assets/source/` | PNG originali: A (colori, fondo chiaro), B (colori, fondo scuro), C (bianco), D (grigio scuro). |
| `assets/logo/` | SVG vettoriali fedeli delle 4 varianti (viewBox 2000×536) e `logo-data.json`. |
| `output/` | MP4 renderizzati, frame finali PNG e cartella `verify/` con il report di corrispondenza. |

File già renderizzati in `output/`:

- `3dtarget-logo-reveal-1920x1080-60fps.mp4`: H.264 High, CRF 14, yuv420p BT.709, 900 frame = 15,00 s, ~33 Mbit/s, audio AAC-LC 320 kbps 48 kHz stereo
- `3dtarget-logo-reveal-1080x1920-60fps.mp4`: stesse specifiche, verticale per i social
- `3dtarget-logo-final-frame-1920x1080.png` / `-1080x1920.png`: frame finale statico

## Render — istruzioni in 5 righe

```bash
npm install                          # Playwright + ffmpeg-static (oppure ffmpeg nel PATH, o FFMPEG=/percorso/ffmpeg)
npx playwright install chromium      # solo la prima volta
npm run render                       # MP4 1920×1080 e 1080×1920 a 60 fps in ./output (+ frame finali PNG)
node render/render.mjs --format h --fps 30 --crf 12   # varianti: formato, fps, qualità, --tagline
npm run verify                       # confronta il frame finale con il PNG originale B → output/verify/
```

Audio (già incluso negli MP4; serve solo per rigenerarlo o cambiarlo):

```bash
pip install numpy scipy matplotlib   # dipendenze della sintesi
npm run audio                        # rigenera audio/*.wav e l'audio incorporato nell'HTML
npm run mux                          # sostituisce l'audio negli MP4 in ./output (video non ricodificato)
```

`npm run render` include automaticamente `audio/3dtarget-logo-audio-mix.wav` se esiste; `--no-audio` per un MP4 muto.

Anteprima: apri `animation/3dtarget-logo-animation.html` in un browser (spazio = play/pausa, ←/→ = frame per frame,
M = audio on/off). L'audio è incorporato (AAC per Safari/Chrome/Edge, Opus per Chromium/Firefox) e fa da clock
master della timeline durante la riproduzione; se il browser blocca l'autoplay parte al primo clic.

## Fedeltà del logo

- Il logo **non è ridisegnato**: ogni elemento (il "3", le 4 staffe, il punto, i 4 segmenti del mirino,
  il divisore, le 8 lettere) è isolato come componente dell'alpha dei PNG ufficiali e vettorializzato
  con potrace su un sovracampionamento ×6. Le forme vengono solo spostate, mascherate o scalate
  in modo uniforme (il punto) durante i reveal, e tornano sempre nella posizione esatta.
- Ogni PNG ha una crenatura leggermente diversa di "Target" (1–5 px): ogni variante è tracciata dal
  proprio file. L'animazione usa la geometria di **B** (stato finale) e di **A** (match-cut chiaro).
- Errore del tracing rispetto ai PNG (alpha, 0–255): medio ≈ 0,43, nessun pixel oltre il 50%.
- Colori campionati dai file: arancione **#FF7800** (non #FF7A00), grigio caldo **#2F2B28**; nella
  variante A il "3" è #2F2B28 mentre mirino, divisore e "Target" sono #2D2D2D (rispettati).
- Frame finale (t = 15,0 s) = variante B su #2F2B28, logo al 58% della larghezza; grana, vignetta,
  aberrazione, glow e bokeh sono a zero. `npm run verify` misura lo scarto rispetto al PNG originale
  ricampionato alla stessa scala (1920×1080: scarto medio 0,09/255, fondo esatto 47,43,40; le
  differenze residue sono solo antialiasing sui bordi, vedi `output/verify/compare-zoom3x-*.png`).

## Timeline

| Tempo | Azione |
|---|---|
| 0,0–2,0 | Buio, grana leggera. Nasce il punto arancione (0,25 s), pulsazione lieve ~1 Hz, alone morbido. |
| 2,0–4,0 | Draw-on delle linee del mirino dal centro (orizzontale 2,00 s, verticale 2,12 s) con testina luminosa; anamorphic flare azzurro-arancio sottile che scorre lento (picco ~3,0 s). |
| 4,0–7,0 | Le 4 staffe della "D" escono dal centro in senso orario (stagger 110 ms), mascherate dal bordo del mirino, da sfocate a nitide; bokeh morbido sullo sfondo con parallasse, bagliore volumetrico. |
| 7,0–9,5 | Il "3" si costruisce in tre fasce da destra verso sinistra (stagger 120 ms); la camera si ricentra sul gruppo "3D" (si ferma a 9,5 s). |
| 9,5–12,0 | Il divisore cresce dal centro; "3D Target" entra con maschera da sinistra, tracking che si stringe e blur→nitido (stagger 90 ms); staffe e "3D" passano dal bianco all'arancione (10,75–12,0 s) con breve bagliore arancione. La camera si allarga sul logo intero. |
| 12,0–12,8 | Match-cut chiaro: un'unica apertura morbida dal punto del mirino verso un fondo bianco caldo con la variante A (pieno a 12,40 s), poi ritorno al fondo scuro con la variante B. Nessuno strobo. |
| 12,7–13,6 | Light sweep diagonale sottile con riflesso sulle lettere; spinta di camera 100% → 104% (12,0–13,5 s). |
| 13,5–15,0 | Hold fermo e nitido; vignetta e grana si dissolvono entro 14,7 s. Tagline opzionale (`--tagline`). |

Easing: `cubic-bezier(0.16, 1, 0.3, 1)` per tutti gli ingressi, sinusoidale morbida per dissolvenze;
camera su spline cubica monotona (velocità continua, nessun overshoot).

## Colonna sonora

Musica e sound design originali, **sintetizzati interamente in codice** (`audio/sound_design.py`): nessun
campione o brano di terzi, quindi nessun problema di licenza. Il risultato è deterministico (seed fissi).

- **Musica:** 120 BPM, così i momenti chiave (2,0 · 4,0 · 7,0 · 9,5 · 12,0 · 13,5 s) cadono sul beat. Tonalità
  di Re: pedale di Re → Si♭maj7 (staffe) → Solm9 (il "3") → La7sus4 in crescendo (divisore e testo) →
  **risoluzione in Re maggiore add9 sul match-cut a 12,0 s**. Pad additivi, ostinato "pluck" con delay ping-pong,
  accordo di piano FM sull'hit con reverse swell, riverbero sintetico.
- **Sound design agganciato alle immagini:** i whoosh del mirino aprono il filtro con la stessa curva di easing
  delle linee e si allargano in stereo come loro; 4 tick ascendenti panoramicati sulle 4 staffe; 3 impatti
  intonati per le 3 fasce del "3"; l'arpeggio delle lettere va da sinistra a destra come il reveal; il glint
  del light sweep attraversa lo stereo con la banda di luce; 70 ms di vuoto prima dell'hit.
- **Master:** 48 kHz / 24 bit, **-16 LUFS integrati, true peak -1,3 dBTP** (ITU-R BS.1770-4). Il limiter
  interviene solo sui due transienti principali (max 2,6 dB, 0,4 s in tutto). Silenzio esatto a 15,0 s.
  Per le piattaforme social che normalizzano a -14 LUFS basta un +2 dB in montaggio.
- **Stem per il montaggio:** `audio/stems/music.wav` e `sfx.wav` (stesso guadagno del master pre-limiter,
  abbassati entrambi di 1,2 dB per non clippare), per rimixare o sostituire la musica tenendo gli effetti.
- **Verifiche:** `audio/audio-sync-check.png` (forma d'onda e spettrogramma con i marker degli eventi),
  `audio/audio-report.json` (loudness, picchi, cue). Negli MP4 l'audio è allineato al campione (scarto 0,
  misurato per correlazione a 4,0 / 7,0 / 12,0 s).

## Punti di sincronizzazione (usati dalla colonna sonora)

| Timestamp | Evento | Audio |
|---|---|---|
| 00:00.00 | Inizio, buio | Room tone quasi impercettibile in fade-in |
| 00:00.25 | Nascita del punto | Sub bloom morbido + bagliore tonale (Re–La) |
| 00:00.49 / 01.44 | Pulsazione del punto | Battiti sub (accennato / pieno) |
| 00:02.00 | Draw-on orizzontale + flare | Doppio whoosh che si apre in stereo con l'easing |
| 00:02.12 | Draw-on verticale | Whoosh centrale più scuro |
| 00:02.00–04.40 | Lens flare (picco 2,7–3,5 s) | Tono cristallino + aria che scorrono da sinistra a destra |
| 00:04.00 / 04.11 / 04.22 / 04.33 | Ingresso delle 4 staffe | 4 tick di precisione ascendenti (TL, TR, BR, BL) + aria; accordo Si♭maj7 |
| 00:05.25 | Staffe assestate | Lock morbido |
| 00:05.00–09.00 | Simbolo e bokeh | Ostinato a semiminime |
| 00:07.00 / 07.12 / 07.24 | Costruzione del "3" | 3 impatti intonati in crescendo (Sol–Si♭–Re); accordo Solm9 |
| 00:09.50 | Camera ferma su "3D", divisore | Zip verticale + sub; accordo La7sus4, parte il riser; ostinato in crome |
| 00:10.05–10.68 | "3D Target" lettera per lettera | Arpeggio di vetro, 1 nota per lettera, panoramica sinistra → destra |
| 00:10.75–11.97 | Bianco → arancione, bagliore | Swell caldo, filtro che si apre, reverse cymbal da 11,0 s |
| 00:11.93–12.00 | — | 70 ms di vuoto (il riser si taglia) |
| 00:12.00 | **Match-cut chiaro** | **Hit: sub + impatto + accordo di piano Re maggiore add9, reverse swell in entrata** |
| 00:12.00–12.80 | Schermo chiaro | Aria luminosa e armonici alti |
| 00:12.46–12.90 | Ritorno al fondo scuro | Respiro discendente |
| 00:12.72–13.62 | Light sweep | Glint che attraversa lo stereo con la banda di luce |
| 00:13.50 | Camera ferma, hold | Accordo finale tenuto |
| 00:13.90–15.00 | Effetti a zero (14,7 s), fine | Dissolvenza fino al silenzio esatto a 15,0 s |
