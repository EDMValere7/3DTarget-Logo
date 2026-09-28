#!/usr/bin/env node
/**
 * Render frame-by-frame dell'animazione 3D Target → MP4 H.264.
 *
 *   node render/render.mjs                       # 16:9 e 9:16, 60 fps, CRF 14
 *   node render/render.mjs --format h --fps 30   # solo 1920×1080 a 30 fps
 *   node render/render.mjs --still               # solo il frame finale PNG
 *
 * Opzioni:
 *   --format h|v|both   formato (default both)
 *   --fps N             frame al secondo (default 60)
 *   --crf N             qualità x264, più basso = migliore (default 14, max consigliato 16)
 *   --preset P          preset x264 (default slow)
 *   --tagline           mostra "Technology meets efficiency" nel finale
 *   --out DIR           cartella di output (default ./output)
 *   --frames-dir DIR    salva anche i PNG dei singoli frame
 *   --still             renderizza solo il frame finale (t = 15 s) in PNG
 *
 * ffmpeg: usa $FFMPEG se definito, poi il pacchetto ffmpeg-static, poi "ffmpeg" nel PATH.
 * Il tempo viene impostato via window.__setTime(t): l'animazione è una funzione
 * pura del tempo, quindi ogni frame è deterministico (nessun rAF, nessun timer).
 */
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HTML = path.join(ROOT, "animation", "3dtarget-logo-animation.html");

function args() {
  const a = process.argv.slice(2), o = { format: "both", fps: 60, crf: 14, preset: "slow",
    tagline: false, out: path.join(ROOT, "output"), framesDir: null, still: false };
  for (let i = 0; i < a.length; i++) {
    const k = a[i];
    if (k === "--format") o.format = a[++i];
    else if (k === "--fps") o.fps = +a[++i];
    else if (k === "--crf") o.crf = +a[++i];
    else if (k === "--preset") o.preset = a[++i];
    else if (k === "--tagline") o.tagline = true;
    else if (k === "--out") o.out = path.resolve(a[++i]);
    else if (k === "--frames-dir") o.framesDir = path.resolve(a[++i]);
    else if (k === "--still") o.still = true;
    else { console.error("Opzione sconosciuta:", k); process.exit(1); }
  }
  return o;
}

async function findFfmpeg() {
  if (process.env.FFMPEG) return process.env.FFMPEG;
  try { const m = await import("ffmpeg-static"); if (m.default && existsSync(m.default)) return m.default; } catch {}
  return "ffmpeg";
}

async function openPage(browser, format, tagline) {
  const size = format === "v" ? { width: 1080, height: 1920 } : { width: 1920, height: 1080 };
  const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 });
  const url = pathToFileURL(HTML).href + `?render=1&format=${format}${tagline ? "&tagline=1" : ""}`;
  page.on("pageerror", e => { console.error("Errore nella pagina:", e); process.exit(1); });
  await page.goto(url);
  await page.evaluate(() => window.__ready);
  return { page, size };
}

async function renderVideo(browser, format, o, ffmpeg) {
  const { page, size } = await openPage(browser, format, o.tagline);
  const duration = await page.evaluate(() => window.__DURATION);
  const total = Math.round(duration * o.fps);
  const name = `3dtarget-logo-reveal-${size.width}x${size.height}-${o.fps}fps${o.tagline ? "-tagline" : ""}.mp4`;
  const outFile = path.join(o.out, name);
  if (o.framesDir) await mkdir(path.join(o.framesDir, format), { recursive: true });

  const ff = spawn(ffmpeg, [
    "-y", "-hide_banner", "-loglevel", "error",
    "-f", "image2pipe", "-framerate", String(o.fps), "-c:v", "png", "-i", "-",
    "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
    "-c:v", "libx264", "-preset", o.preset, "-crf", String(o.crf),
    "-profile:v", "high", "-level", "5.1",
    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
    "-movflags", "+faststart", "-an", outFile,
  ], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", c => c === 0 ? res() : rej(new Error("ffmpeg exit " + c))));
  ff.on("error", e => { console.error("Impossibile avviare ffmpeg:", e.message); process.exit(1); });

  const t0 = Date.now();
  // frame 0 … total: l'ultimo frame (t = 15,0 s) è esattamente il logo finale
  for (let i = 0; i <= total; i++) {
    const t = Math.min(duration, i / o.fps);
    await page.evaluate(tt => window.__setTime(tt), t);
    const buf = await page.screenshot({ type: "png", animations: "disabled" });
    if (o.framesDir) await writeFile(path.join(o.framesDir, format, `f${String(i).padStart(5, "0")}.png`), buf);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (i % o.fps === 0 || i === total) {
      const el = (Date.now() - t0) / 1000;
      process.stdout.write(`\r[${format}] frame ${i}/${total}  ${(i / Math.max(el, 0.001)).toFixed(1)} fps  `);
    }
  }
  ff.stdin.end();
  await done;
  await page.close();
  console.log(`\n→ ${path.relative(process.cwd(), outFile)}`);
}

async function renderStill(browser, format, o) {
  const { page, size } = await openPage(browser, format, o.tagline);
  await page.evaluate(() => window.__setTime(window.__DURATION));
  const file = path.join(o.out, `3dtarget-logo-final-frame-${size.width}x${size.height}${o.tagline ? "-tagline" : ""}.png`);
  await page.screenshot({ path: file, type: "png" });
  await page.close();
  console.log(`→ ${path.relative(process.cwd(), file)}`);
}

const o = args();
await mkdir(o.out, { recursive: true });
const formats = o.format === "both" ? ["h", "v"] : [o.format];
const browser = await chromium.launch();
try {
  if (o.still) for (const f of formats) await renderStill(browser, f, o);
  else {
    const ffmpeg = await findFfmpeg();
    for (const f of formats) { await renderVideo(browser, f, o, ffmpeg); await renderStill(browser, f, o); }
  }
} finally {
  await browser.close();
}
