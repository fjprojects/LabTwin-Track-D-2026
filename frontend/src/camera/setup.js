export class CameraSetupError extends Error {}

export function cameraErrorText(error) {
  if (error instanceof CameraSetupError) return error.message;
  const messages = {
    NotAllowedError: "Camera permission was denied. You can continue the assessment. If you want to retry, allow camera access in this site's browser settings and check your device privacy settings.",
    NotFoundError: "No camera was found. Connect a camera or continue without camera cues.",
    NotReadableError: "The camera could not be opened. Close other apps using it, check device permissions, and retry if you choose. You can continue without camera cues.",
    OverconstrainedError: "This camera could not use the requested settings. Try another camera or continue without camera cues.",
    SecurityError: "Camera access needs HTTPS or localhost and permission from your browser. You can continue without camera cues.",
    AbortError: "Camera startup was interrupted. Retry if you choose; your answers remain available.",
  };
  // Browser/provider exceptions may contain device names or internal paths.
  return messages[error?.name] || "Camera setup is temporarily unavailable. You can retry or continue the assessment without camera cues.";
}

export function within(promise, milliseconds, message, onLateResult = () => {}) {
  let expired = false, timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => { expired = true; reject(new CameraSetupError(message)); }, milliseconds);
  });
  const result = Promise.resolve(promise).then(value => {
    if (expired) onLateResult(value);
    return value;
  });
  return Promise.race([result, deadline]).finally(() => clearTimeout(timer));
}
