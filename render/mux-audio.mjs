#!/usr/bin/env node
/**
 * Aggiunge (o sostituisce) la colonna sonora negli MP4 già renderizzati,
 * senza ricodificare il video (stream copy).
 *
 *   node render/mux-audio.mjs                 # tutti gli MP4 in ./output
 *   node render/mux-audio.mjs file1.mp4 …     # file specifici
 *
 * Audio: audio/3dtarget-logo-audio-mix.wav (generato da audio/sound_design.py)
 * → AAC-LC 320 kbps, 48 kHz stereo.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, renameSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const AUDIO = path.join(ROOT, "audio", "3dtarget-logo-audio-mix.wav");

export async function findFfmpeg() {
  if (process.env.FFMPEG) return process.env.FFMPEG;
  try { const m = await import("ffmpeg-static"); if (m.default && existsSync(m.default)) return m.default; } catch {}
  return "ffmpeg";
}

export function muxFile(ffmpeg, file) {
  const tmp = file.replace(/\.mp4$/, ".mux-tmp.mp4");
  const r = spawnSync(ffmpeg, [
    "-y", "-hide_banner", "-loglevel", "error",
    "-i", file, "-i", AUDIO,
    "-map", "0:v:0", "-map", "1:a:0",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
    "-movflags", "+faststart", tmp,
  ], { stdio: "inherit" });
  if (r.status !== 0) throw new Error("ffmpeg ha restituito " + r.status + " su " + file);
  renameSync(tmp, file);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  if (!existsSync(AUDIO)) {
    console.error("Manca", path.relative(process.cwd(), AUDIO), "— esegui prima: python3 audio/sound_design.py");
    process.exit(1);
  }
  const ffmpeg = await findFfmpeg();
  const outDir = path.join(ROOT, "output");
  const files = process.argv.length > 2 ? process.argv.slice(2).map(f => path.resolve(f))
    : readdirSync(outDir).filter(f => f.endsWith(".mp4") && !f.includes(".mux-tmp")).map(f => path.join(outDir, f));
  for (const f of files) { muxFile(ffmpeg, f); console.log("→", path.relative(process.cwd(), f)); }
}
