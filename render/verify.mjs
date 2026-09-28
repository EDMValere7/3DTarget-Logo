#!/usr/bin/env node
/**
 * Verifica il frame finale dell'animazione contro il PNG originale (variante B).
 *
 *   node render/verify.mjs [--format h|v]
 *
 * 1. renderizza il frame a t = 15,0 s;
 * 2. renderizza un frame di riferimento: il PNG originale "logo-B-color-dark.png"
 *    su fondo #2F2B28, con la stessa scala/posizione del logo finale;
 * 3. confronta i due pixel per pixel e scrive in output/verify/:
 *    - final-frame.png, reference.png
 *    - diff.png (differenza assoluta amplificata ×4)
 *    - compare.png (ingrandimento 3× affiancato: animazione | originale | diff)
 *    - report.json (metriche)
 */
import { chromium } from "playwright";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HTML = path.join(ROOT, "animation", "3dtarget-logo-animation.html");
const SRC = path.join(ROOT, "assets", "source", "logo-B-color-dark.png");
const OUT = path.join(ROOT, "output", "verify");
const fmt = process.argv.includes("--format") ? process.argv[process.argv.indexOf("--format") + 1] : "h";
const size = fmt === "v" ? { width: 1080, height: 1920 } : { width: 1920, height: 1080 };

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 });

// 1. frame finale
await page.goto(pathToFileURL(HTML).href + `?render=1&format=${fmt}`);
await page.evaluate(() => window.__ready);
await page.evaluate(() => window.__setTime(window.__DURATION));
const tr = await page.evaluate(() => window.__finalTransform());
const finalPng = await page.screenshot({ type: "png" });

// 2. riferimento: PNG originale posizionato con la stessa trasformazione
const srcB64 = (await readFile(SRC)).toString("base64");
await page.setContent(`<style>html,body{margin:0;background:#2F2B28;overflow:hidden}
  img{position:absolute;left:0;top:0;transform-origin:0 0;
  transform:matrix(${tr.s},0,0,${tr.s},${tr.tx},${tr.ty})}</style>
  <img src="data:image/png;base64,${srcB64}">`);
await page.waitForFunction(() => document.images[0].complete);
const refPng = await page.screenshot({ type: "png" });

// 3. confronto (nel browser, via canvas)
const result = await page.evaluate(async ({ a, b, W, H, box }) => {
  const load = async s => { const im = new Image(); im.src = "data:image/png;base64," + s; await im.decode(); return im; };
  const [ia, ib] = await Promise.all([load(a), load(b)]);
  const cv = (w, h) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  const ca = cv(W, H), cb = cv(W, H);
  ca.getContext("2d").drawImage(ia, 0, 0); cb.getContext("2d").drawImage(ib, 0, 0);
  const da = ca.getContext("2d").getImageData(0, 0, W, H).data, db = cb.getContext("2d").getImageData(0, 0, W, H).data;
  const cd = cv(W, H), dctx = cd.getContext("2d"), dd = dctx.createImageData(W, H);
  let sum = 0, max = 0, n8 = 0, n32 = 0, n64 = 0, inBox = 0, bg = 0;
  for (let i = 0; i < da.length; i += 4) {
    const d = Math.max(Math.abs(da[i] - db[i]), Math.abs(da[i + 1] - db[i + 1]), Math.abs(da[i + 2] - db[i + 2]));
    sum += d; if (d > max) max = d; if (d > 8) n8++; if (d > 32) n32++; if (d > 64) n64++;
    const v = Math.min(255, d * 4); dd.data[i] = v; dd.data[i + 1] = v * 0.47; dd.data[i + 2] = 0; dd.data[i + 3] = 255;
    const p = i / 4, x = p % W, y = (p / W) | 0;
    if (x >= box[0] && x < box[2] && y >= box[1] && y < box[3]) inBox++;
  }
  // colore del fondo nel frame finale (angolo)
  bg = [da[0], da[1], da[2]];
  dctx.putImageData(dd, 0, 0);
  // compare: crop ingrandito 3× attorno al simbolo
  const [cx0, cy0, cw, ch] = box[4];
  const cmp = cv(cw * 3 * 3 + 40, ch * 3), k = cmp.getContext("2d");
  k.imageSmoothingEnabled = false; k.fillStyle = "#111"; k.fillRect(0, 0, cmp.width, cmp.height);
  [ca, cb, cd].forEach((c, j) => k.drawImage(c, cx0, cy0, cw, ch, j * (cw * 3 + 20), 0, cw * 3, ch * 3));
  return {
    pixels: W * H, meanAbsDiff: +(sum / (W * H)).toFixed(4), maxDiff: max,
    pixelsOver8: n8, pixelsOver32: n32, pixelsOver64: n64, background: bg,
    diff: cd.toDataURL("image/png").split(",")[1], compare: cmp.toDataURL("image/png").split(",")[1],
  };
}, { a: finalPng.toString("base64"), b: refPng.toString("base64"), W: size.width, H: size.height,
     box: [0, 0, size.width, size.height,
       [Math.round(tr.tx + 380 * tr.s), Math.round(tr.ty + 80 * tr.s), Math.round(460 * tr.s), Math.round(380 * tr.s)]] });

await browser.close();
const tag = `${size.width}x${size.height}`;
await writeFile(path.join(OUT, `final-frame-${tag}.png`), finalPng);
await writeFile(path.join(OUT, `reference-${tag}.png`), refPng);
await writeFile(path.join(OUT, `diff-x4-${tag}.png`), Buffer.from(result.diff, "base64"));
await writeFile(path.join(OUT, `compare-zoom3x-${tag}.png`), Buffer.from(result.compare, "base64"));
delete result.diff; delete result.compare;
const report = { format: tag, finalTransform: tr, ...result,
  note: "Differenze = scarto 0-255 sul canale peggiore tra frame vettoriale finale e PNG originale B ricampionato alla stessa scala." };
await writeFile(path.join(OUT, `report-${tag}.json`), JSON.stringify(report, null, 2));
console.log(report);
