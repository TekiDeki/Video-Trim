# Video Trimmer

Cut a video in the browser. Pick the start and the end, optionally drop the sound, save a smaller
file. **The clip never leaves the device** — there is no server, no account, no upload.

Live: <https://tekideki.github.io/Video-Trim/>

## Why it exists

Every "trim a video" page online uploads your file somewhere. This one does not: the page decodes
and re-encodes the video itself, with the browser's own engine (`MediaRecorder` + `WebAudio`), and
writes the result straight back to you as a download. Unplug the network after the page loads and it
still works.

## What it does

- keeps the part between the start and end point, and nothing else;
- optionally removes the audio track;
- three size/quality levels (about 8, 3.5 and 1.2 Mbit/s of video);
- writes WebM (VP9/VP8 + Opus), or MP4 (H.264 + AAC) where the browser can record it — Safari;
- **Save this frame**: a PNG of the current picture, with no re-encoding at all;
- offline after the first load (service worker), light and dark theme, keyboard accessible.

## What it does not do

Joining clips, titles, transitions, changing the resolution. It is a trimmer, not an editor. For
editing, see `Cutline` (the open-source editor this page took its approach from — vanilla JS,
WebCodecs/WebGL, no build step).

## The one honest cost

A browser cannot copy a slice out of a compressed video without decoding it, so the tool **plays the
kept part once and records it again**. A 30-second cut takes about 30 seconds. During the export the
sound is routed away from the speakers (captured through `WebAudio`, not played).

## How it is built

One file, no build step, no dependencies: `index.html` holds the CSS and the JavaScript. No network
requests at runtime, no cookies, no analytics. `service-worker.js` caches the shell for offline use.
Content Security Policy comes from a `<meta>` tag, because GitHub Pages cannot send headers.

## Tests

```bash
python3 tests/test_video.py            # local, headless Chromium
python3 tests/test_video.py --live     # against the published page
```

The test makes a real video in the page (canvas + `MediaRecorder`), loads it into the tool, trims it,
exports it and checks the output: non-empty, right container, right length, no console errors, no
horizontal scroll at 320px, and every tap target at least 44×44 px on a touch screen.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
