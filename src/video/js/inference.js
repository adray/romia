"use strict";

// pts: [{x,y,z}] normalized MediaPipe coords. w,h = source image size.
function rotateHead(pts, yaw, pitch, roll, pivot, w, h) {
  const cy = Math.cos(yaw),   sy = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  const cr = Math.cos(roll),  sr = Math.sin(roll);
  return pts.map(p => {
    // to pixel-ish space, with z on the same scale as x
    let x = (p.x - pivot.x) * w, y = (p.y - pivot.y) * h, z = (p.z - pivot.z) * w;
    // yaw (around vertical axis)
    [x, z] = [cy * x + sy * z, -sy * x + cy * z];
    // pitch (around horizontal axis)
    [y, z] = [cp * y - sp * z, sp * y + cp * z];
    // roll (in the image plane)
    [x, y] = [cr * x - sr * y, sr * x + cr * y];
    return { x: x / w + pivot.x, y: y / h + pivot.y, z: z / w + pivot.z };
  });
}


// Same pixel mapping as drawing_utils: floor, clamp, skip anything outside [0,1]
function toPx(p, w, h) {
  if (!(p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)) return null;
  return [Math.min(Math.floor(p.x * w), w - 1) + 0.5,   // +0.5: canvas pixel centres
          Math.min(Math.floor(p.y * h), h - 1) + 0.5];
}

function renderFrame(style, ctx, face, pose, w, h) {
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);
  ctx.lineCap = "round";
  for (const layer of style) {
    const lms = layer.lm === "face" ? face : pose;
    // Python skips landmarks with visibility or presence < 0.5.
    // Fields that are absent (your face JSON) compare false, so those pass.
    const px = lms.map(p => (p.visibility < 0.5 || p.presence < 0.5) ? null : toPx(p, w, h));

    for (const [a, b, c, t] of layer.edges) {
      if (!px[a] || !px[b]) continue;          // both endpoints must exist
      ctx.strokeStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
      ctx.lineWidth = t/4;
      ctx.beginPath(); ctx.moveTo(...px[a]); ctx.lineTo(...px[b]); ctx.stroke();
    }
  }


  for (const layer of style) {
    const lms = layer.lm === "face" ? face : pose;
    const px = lms.map(p => (p.visibility < 0.5 || p.presence < 0.5) ? null : toPx(p, w, h));
    if (layer.points) {                         // pose joint dots
      px.forEach((q, i) => {
        const s = layer.points[i];
        if (!q || !s) return;
        const r = s.radius, rb = Math.max(r + 1, Math.floor(r * 1.2));
        ctx.lineWidth = s.thickness/4;
        ctx.strokeStyle = "rgb(224,224,224)";   // white border ring
        ctx.beginPath(); ctx.arc(q[0], q[1], rb, 0, 6.2832); ctx.stroke();
        ctx.strokeStyle = `rgb(${s.color})`;    // coloured ring on top
        ctx.beginPath(); ctx.arc(q[0], q[1], r, 0, 6.2832); ctx.stroke();
      });
    }
  }
}

async function imageToTensor(url_rgb, url_alpha, size = 256, channels = 3) {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = url_rgb;
    await img.decode();

    const img_alpha = new Image();
    img_alpha.crossOrigin = 'anonymous';
    img_alpha.src = url_alpha;
    await img_alpha.decode();

    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, size, size);
    const { data } = ctx.getImageData(0, 0, size, size); // RGBA, 0-255

    const alphaCanvas = document.createElement('canvas');
    alphaCanvas.width = alphaCanvas.height = size;
    const alphaCtx = alphaCanvas.getContext('2d');
    alphaCtx.drawImage(img_alpha, 0, 0, size, size);
    const { data: alphaData } = alphaCtx.getImageData(0, 0, size, size); // RGBA, 0-255

    const floats = new Float32Array(size * size * channels);
    for (let i = 0, j = 0; i < data.length; i += 4) {
        floats[j++] = data[i]     / 127.5 - 1;  // R
        floats[j++] = data[i + 1] / 127.5 - 1;  // G
        floats[j++] = data[i + 2] / 127.5 - 1;  // B
        if (channels === 4) {
            floats[j++] = alphaData[i] / 127.5 - 1;  // A
        }
    }
    return new ort.Tensor('float32', floats, [1, size, size, channels]); // NHWC
}

function displayResult(canvas, elementId) {
    const dataUrl = canvas.toDataURL();
    const imageElement = document.querySelector(elementId);
    imageElement.src = dataUrl;
}

function diffCanvas(canvas1, canvas2, width, height) {
    const ctx = canvas1.getContext('2d');
    const data1 = ctx.getImageData(0, 0, width, height).data;
    const ctx2 = canvas2.getContext('2d');
    const data2 = ctx2.getImageData(0, 0, width, height).data;

    const resultCanvas = document.createElement('canvas');
    resultCanvas.width = width;
    resultCanvas.height = height;

    const resultCtx = resultCanvas.getContext('2d');
    const imageData = resultCtx.createImageData(width, height);
    for (let i = 0; i < imageData.data.length; i += 4) {
        const rDiff = data1[i] - data2[i];
        const gDiff = data1[i + 1] - data2[i + 1];
        const bDiff = data1[i + 2] - data2[i + 2];
        const diff = rDiff * rDiff + gDiff * gDiff + bDiff * bDiff;
        const val = Math.min(255, Math.sqrt(diff));
        imageData.data[i] = val;
        imageData.data[i + 1] = val;
        imageData.data[i + 2] = val;
        imageData.data[i + 3] = 255;
    }
    resultCtx.putImageData(imageData, 0, 0);
    return resultCanvas;
}

async function loadTruth(url) {
    const truthImg = new Image();
    truthImg.crossOrigin = 'anonymous';
    truthImg.src = url;
    await truthImg.decode();
    const truthCanvas = document.createElement('canvas');
    truthCanvas.width = 640;
    truthCanvas.height = 640;
    const truthCtx = truthCanvas.getContext('2d');
    truthCtx.drawImage(truthImg, 0, 0, 640, 640);

    // Downscale the truth canvas to 320x320 for comparison
    const downscaleCanvas = document.createElement('canvas');
    downscaleCanvas.width = 320;
    downscaleCanvas.height = 320;
    const downscaleCtx = downscaleCanvas.getContext('2d');
    downscaleCtx.drawImage(truthCanvas, 0, 0, 320, 320);

    return downscaleCanvas;
}

// use an async context to call onnxruntime functions.
async function main() {
    // Check for GPU support
    console.log('gpu' in navigator);                    // should be true
    const adapter = await navigator.gpu?.requestAdapter();
    console.log(adapter ? 'adapter found' : 'no adapter');

    const style = await fetch("/gan/Romia/render_style.json").then(res => res.json());
    const landmarks = await fetch('/gan/Romia/landmarks.json').then(res => res.json());
    const face_landmarks = landmarks.face;
    const pose_landmarks = landmarks.pose;

    const truthImageURL = '/gan/Romia/frame_000001_t0.000s_data.png';
    const truthCanvas = await loadTruth(truthImageURL);

    // Rotate head landmarks based on yaw, pitch, roll
    const yaw = 0.1;   // example values
    const pitch = 0.1;
    const roll = 0.1;
    const pivot = { x: 0.5, y: 0.5, z: 0 };
    const w = 320;
    const h = 320;
    const rotated_face_landmarks = rotateHead(face_landmarks, yaw, pitch, roll, pivot, w, h);

    const landmarksCanvas = document.createElement('canvas');
    landmarksCanvas.width = w;
    landmarksCanvas.height = h;
    const ctx = landmarksCanvas.getContext('2d');
    renderFrame(style,ctx, face_landmarks, pose_landmarks, w, h);

    const diffCanvasResult = diffCanvas(landmarksCanvas, truthCanvas, w, h);
    displayResult(diffCanvasResult, "#diff-img");
    displayResult(landmarksCanvas, "#landmarks-img");

    var msg = "";
    try {
        // create a new session and load the specific model.
        //
        const session = await ort.InferenceSession.create('/gan/Romia/generator.onnx',
            { executionProviders: ["webgpu", 'wasm'] }
        );

        const sourceImageURL1 = landmarksCanvas.toDataURL();
        const sourceImageURL2 = '/gan/Romia/frame_000001_t0.000s.png';

        const inputName = session.inputNames[0];
        const outputName = session.outputNames[0];

        const width = 320;
        const height = 320;

        // prepare inputs. a tensor need its corresponding TypedArray as data
        const tensor = await imageToTensor(sourceImageURL1, sourceImageURL2, width, 4);
        msg = `tensor size: ${tensor.dims}`;

        // prepare feeds. use model input names as keys.
        const feeds = { [inputName]: tensor };

        // feed inputs and run
        const results = await session.run(feeds);

        // read from results
        const dataOutput = results[outputName].data;
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        const imageData = ctx.createImageData(width, height);
        for (let i = 0, j = 0; i < imageData.data.length; i += 4, j += 3) {
            imageData.data[i]     = (dataOutput[j]     + 1) * 127.5;
            imageData.data[i + 1] = (dataOutput[j + 1] + 1) * 127.5;
            imageData.data[i + 2] = (dataOutput[j + 2] + 1) * 127.5;
            imageData.data[i + 3] = 255;
        }
        ctx.putImageData(imageData, 0, 0);
        displayResult(canvas, "#gan-img");

        session.release();

    } catch (e) {
        document.write(`failed to inference ONNX model: ${e} ${msg}.`);
    }
}

main();