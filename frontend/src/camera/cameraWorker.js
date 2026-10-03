import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { poseFromLandmarks } from "./cuePolicy.js";

let detector = null;
self.onmessage = async ({ data }) => {
  try {
    if (data.type === "init") {
      const files = await FilesetResolver.forVisionTasks(data.wasmUrl);
      detector = await FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: data.modelUrl, delegate: "CPU" },
        runningMode: "VIDEO", numFaces: 1, minFaceDetectionConfidence: 0.6,
        minFacePresenceConfidence: 0.6, minTrackingConfidence: 0.6,
        outputFaceBlendshapes: false, outputFacialTransformationMatrixes: false,
      });
      self.postMessage({ type: "ready" });
    } else if (data.type === "frame" && detector) {
      try {
        const result = detector.detectForVideo(data.frame, data.timestamp);
        // Only disposable ratios leave this worker. No frame, image, identity,
        // landmark array or biometric template goes to the backend.
        self.postMessage({ type: "sample", pose: poseFromLandmarks(result.faceLandmarks[0]), timestamp: data.timestamp });
      } finally { data.frame.close(); }
    }
  } catch { self.postMessage({ type: "error", message: "Camera analysis could not run. Your assessment remains available." }); }
};
