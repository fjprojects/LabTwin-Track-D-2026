import { cp, mkdir, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Pinned npm runtime and bundled official model are served from LabTwin itself.
// A student's browser never needs to send camera frames to a third-party CDN.
const root = fileURLToPath(new URL("../", import.meta.url));
await access(`${root}public/camera/face_landmarker.task`);
await mkdir(`${root}public/camera/wasm`, { recursive: true });
await cp(`${root}node_modules/@mediapipe/tasks-vision/wasm`, `${root}public/camera/wasm`, { recursive: true });
console.log("Local assessment camera assets ready.");
