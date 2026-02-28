const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("preview");
const predictBtn = document.getElementById("predictBtn");
const useCamera = document.getElementById("useCamera");
const captureBtn = document.getElementById("captureBtn");
const resultCard = document.getElementById("resultCard");
const labelEl = document.getElementById("label");
const confBar = document.getElementById("confBar");
const confText = document.getElementById("confText");
const loader = document.getElementById("loader");
const modelVersionEl = document.getElementById("modelVersion");
const lowWarningEl = document.getElementById("lowWarning");
const feedbackBtn = document.getElementById("feedbackBtn");

let currentBlob = null;
let stream = null;
let videoEl = null;

fileInput.addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const url = URL.createObjectURL(f);
  preview.src = url;
  currentBlob = f;
  showCapture(false);
});

useCamera.addEventListener("click", async () => {
  if (stream) {
    stopCamera();
    return;
  }
  videoEl = document.createElement("video");
  videoEl.autoplay = true;
  videoEl.playsInline = true;
  preview.src = "";
  preview.style.display = "none";
  const holder = document.querySelector(".uploader");
  holder.appendChild(videoEl);
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: 640 }, audio: false });
    videoEl.srcObject = stream;
    showCapture(true);
  } catch (err) {
    alert("Camera access denied or not available.");
  }
});

captureBtn.addEventListener("click", async () => {
  if (!videoEl) return;
  const canvas = document.createElement("canvas");
  canvas.width = videoEl.videoWidth || 640;
  canvas.height = videoEl.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
  preview.src = dataUrl;
  preview.style.display = "block";
  if (videoEl && videoEl.parentNode) videoEl.parentNode.removeChild(videoEl);
  stopCamera(false);
  currentBlob = dataURLtoBlob(dataUrl);
  showCapture(false);
});

predictBtn.addEventListener("click", async () => {
  if (!currentBlob) return alert("Please upload or capture an image first.");
  setLoading(true);
  try {
    if (currentBlob instanceof Blob && currentBlob.type) {
      const fd = new FormData();
      fd.append("file", currentBlob, "image.jpg");
      const res = await fetch("/predict", { method: "POST", body: fd });
      const j = await res.json();
      showResult(j);
    } else {
      const reader = new FileReader();
      reader.onloadend = async () => {
        const frame = reader.result;
        const res = await fetch("/predict-frame", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ frame }),
        });
        const j = await res.json();
        showResult(j);
      };
      reader.readAsDataURL(currentBlob);
    }
  } catch (err) {
    alert("Prediction failed: " + (err.message || err));
  } finally {
    setLoading(false);
  }
});

function showResult(j){
  resultCard.hidden = false;
  labelEl.textContent = j.disease || "Unknown";
  confBar.style.width = (j.confidence || 0) + "%";
  confText.textContent = (j.confidence || 0) + "%";
  // show model version if provided
  if (j.model_version && modelVersionEl) modelVersionEl.textContent = j.model_version;
  // show low confidence warning
  if (typeof j.low_confidence !== 'undefined' && lowWarningEl){
    lowWarningEl.style.display = j.low_confidence ? 'block' : 'none';
  }
  // store last prediction id for feedback
  resultCard.dataset.predId = j.id || '';
  // enable feedback button
  if (feedbackBtn) feedbackBtn.disabled = false;
}

if (feedbackBtn){
  feedbackBtn.addEventListener('click', async ()=>{
    const predId = resultCard.dataset.predId;
    if (!predId) return alert('No prediction id available to feedback.');
    const trueLabel = prompt('Enter the correct label (exact class name):');
    if (!trueLabel) return;
    try{
      const res = await fetch(`/feedback/${predId}`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ true_label: trueLabel, predicted_label: labelEl.textContent }) });
      const j = await res.json();
      alert('Feedback recorded. Current accuracy: ' + (j.accuracy || 'N/A'));
    }catch(e){ alert('Feedback failed: ' + (e.message||e)); }
  });
}

function setLoading(v){
  loader.hidden = !v;
  predictBtn.disabled = v;
  captureBtn.disabled = v;
  fileInput.disabled = v;
}

function showCapture(yes){
  captureBtn.hidden = !yes;
  if (!yes && videoEl && videoEl.parentNode) { videoEl.parentNode.removeChild(videoEl); videoEl = null; }
}

function stopCamera(remove=true){
  if (!stream) return;
  stream.getTracks().forEach(t=>t.stop());
  stream = null;
  if (remove && videoEl && videoEl.parentNode){ videoEl.parentNode.removeChild(videoEl); videoEl=null; }
  preview.style.display = "block";
}

function dataURLtoBlob(dataurl) {
  var arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
      bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
  while(n--){ u8arr[n] = bstr.charCodeAt(n); }
  return new Blob([u8arr], {type:mime});
}
