const API = "http://127.0.0.1:5002";

let currentSessionId = null;
let mediaRecorder = null;
let recordedChunks = [];
let stream = null;

// ========== TAB SWITCHING ==========
function switchTab(tabName) {
  // Show correct section
  document.querySelectorAll(".tab-section").forEach((sec) =>
    sec.classList.remove("show")
  );
  document.getElementById(tabName).classList.add("show");

  // Highlight correct tab button
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const onclick = btn.getAttribute("onclick") || "";
    if (onclick.includes(`'${tabName}'`)) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

// ========== SECTION 1: TAKE EXAM ==========
async function startExam() {
  const studentId = document.getElementById("studentId").value.trim();
  const examId = document.getElementById("examId").value.trim();
  
  if (!studentId || !examId) {
    showStatus("examStatus", "❌ Please enter Student ID and Exam ID", "error");
    return;
  }
  
  try {
    // Generate session ID
    currentSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Initialize exam session on backend
    const initRes = await fetch(`${API}/start-exam`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        sessionId: currentSessionId, 
        studentId, 
        examId 
      })
    });
    
    const initData = await initRes.json();
    
    if (initData.status !== "success") {
      throw new Error(initData.error || "Failed to start exam");
    }
    
    // Get camera and microphone access
    stream = await navigator.mediaDevices.getUserMedia({ 
      video: true, 
      audio: true 
    });
    
    const videoElement = document.getElementById("videoPreview");
    videoElement.srcObject = stream;
    videoElement.classList.add("active");
    
    // Setup MediaRecorder
    recordedChunks = [];
    const options = { mimeType: 'video/webm;codecs=vp9' };
    
    try {
      mediaRecorder = new MediaRecorder(stream, options);
    } catch (e) {
      // Fallback if vp9 not supported
      mediaRecorder = new MediaRecorder(stream);
    }
    
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        recordedChunks.push(e.data);
      }
    };
    
    mediaRecorder.start();
    
    // Update UI
    document.getElementById("startExamBtn").disabled = true;
    document.getElementById("submitExamBtn").disabled = false;
    document.getElementById("studentId").disabled = true;
    document.getElementById("examId").disabled = true;
    document.getElementById("recordingIndicator").classList.add("active");
    
    // Update session info for encryption tab
    updateSessionInfo(studentId, examId);
    
    showStatus(
      "examStatus",
      "✅ Exam started! Video recording in progress. Answer questions and click Submit when done.",
      "success"
    );
    
  } catch (error) {
    showStatus("examStatus", `❌ Error: ${error.message}`, "error");
    console.error(error);
  }
}

async function submitExam() {
  if (!mediaRecorder || !currentSessionId) {
    showStatus("examStatus", "❌ Exam not started", "error");
    return;
  }
  
  showStatus("examStatus", "⏳ Submitting exam, saving video, and encrypting...", "loading");
  
  // Stop recording
  mediaRecorder.stop();
  
  // Wait for all data to be collected
  await new Promise((resolve) => {
    mediaRecorder.onstop = resolve;
  });
  
  // Stop camera
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    const videoElement = document.getElementById("videoPreview");
    videoElement.classList.remove("active");
    videoElement.srcObject = null;
  }
  
  // Create video blob
  const videoBlob = new Blob(recordedChunks, { type: "video/webm" });
  
  // Get exam answers
  const examAnswers = document.getElementById("examAnswers").value.trim();
  
  // Create FormData
  const formData = new FormData();
  formData.append("sessionId", currentSessionId);
  formData.append("video", videoBlob, "exam_recording.webm");
  formData.append("examAnswers", JSON.stringify({ answers: examAnswers }));
  
  try {
    const res = await fetch(`${API}/submit-exam`, {
      method: "POST",
      body: formData,
    });
    
    const result = await res.json();
    
    if (result.status === "success") {
      // -------- EXAM SUMMARY --------
      const outputData = {
        "Status": "✅ EXAM SUBMITTED & ENCRYPTED",
        "Session ID": currentSessionId,
        "Filename": result.filename,
        "File Size (MB)": (result.fileSize / 1024 / 1024).toFixed(2),
        "Original Video Hash (SHA-256)": result.fileHash.substring(0, 32) + "...",
        "Next Step": "Encryption details have been generated automatically. Check the 'Encryption Details' tab."
      };
      
      document.getElementById("examOutput").textContent = JSON.stringify(outputData, null, 2);
      showStatus(
        "examStatus",
        "✅ Exam submitted and encrypted successfully!",
        "success"
      );
      
      // -------- ENCRYPTION DETAILS --------
      const enc = result.encryption;
      if (enc) {
        const approxMB = enc.ciphertextSize
          ? (enc.ciphertextSize / 2 / 1024 / 1024).toFixed(2)
          : "N/A";
        
        const encDisplay = {
          "Status": "✅ ENCRYPTED & SIGNED (AUTO AFTER SUBMIT)",
          "Session ID": currentSessionId,
          "Algorithms": enc.algorithms || "AES-256-GCM + RSA-PSS + SHA-256",
          "Encrypted File": enc.encryptedFile,
          "Session Key (SAVE THIS!)": enc.sessionKey,
          "IV (Hex)": enc.iv,
          "GCM Tag (Hex)": enc.tag,
          "Original Video Hash (SHA-256)": enc.fileHash.substring(0, 32) + "...",
          "Exam Data Hash (SHA-256)": enc.dataHash.substring(0, 32) + "...",
          "RSA Signature (Base64)": enc.signature.substring(0, 40) + "...",
          "Ciphertext Size (approx)": `${approxMB} MB (hex length: ${enc.ciphertextSize})`,
          "⚠️ IMPORTANT": "Copy and securely store the Session Key above. It is required for decryption."
        };
        
        document.getElementById("encryptOutput").textContent = JSON.stringify(
          encDisplay,
          null,
          2
        );
        showStatus(
          "encryptStatus",
          "🔐 Video encrypted & exam data signed automatically after submission.",
          "success"
        );
        
        // Auto-fill session key in decrypt tab
        document.getElementById("sessionKeyInput").value = enc.sessionKey;
        
        // Now integrity verification & decryption are allowed
        document.getElementById("verifyBtn").disabled = false;
        document.getElementById("decryptBtn").disabled = false;
        
        // Switch to Encryption tab so user can see details
        switchTab("encrypt");
      }
      
      // Disable submit button after done
      document.getElementById("submitExamBtn").disabled = true;
      document.getElementById("recordingIndicator").classList.remove("active");
      
    } else {
      showStatus("examStatus", `❌ Submission failed: ${result.error}`, "error");
      document.getElementById("recordingIndicator").classList.remove("active");
    }
    
  } catch (error) {
    showStatus("examStatus", `❌ Error: ${error.message}`, "error");
    document.getElementById("recordingIndicator").classList.remove("active");
    console.error(error);
  }
}

function updateSessionInfo(studentId, examId) {
  document.getElementById("sessionInfo").textContent =
    `Session: ${currentSessionId}\nStudent: ${studentId}\nExam: ${examId}`;
}

// ========== SECTION 3: TAMPER DETECTION ==========
async function verifyIntegrity() {
  if (!currentSessionId) {
    showStatus("verifyStatus", "❌ No session to verify. Complete Section 1 first.", "error");
    return;
  }
  
  showStatus("verifyStatus", "🔍 Verifying video hash and digital signature...", "loading");
  
  try {
    const res = await fetch(`${API}/verify-integrity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId: currentSessionId })
    });
    
    const result = await res.json();
    
    if (result.status === "success") {
      const verification = result.verification;
      
      const displayData = {
        "🔍 Overall Status": verification.status,
        "🎥 Video Integrity": verification.videoTampered ? "❌ TAMPERED" : "✅ INTACT",
        "📋 Data Integrity": verification.dataTampered ? "❌ TAMPERED" : "✅ INTACT",
        "✍️ Digital Signature": verification.signatureValid ? "✅ VALID" : "❌ INVALID",
        "Details": {
          "Student ID": result.details.studentId,
          "Exam ID": result.details.examId,
          "Original Video Hash": result.details.originalVideoHash.substring(0, 32) + "...",
          "Original Data Hash": String(result.details.originalDataHash).substring(0, 32) + "...",
          "Signature Present": result.details.signaturePresent ? "Yes" : "No"
        }
      };
      
      document.getElementById("verifyOutput").textContent = JSON.stringify(
        displayData,
        null,
        2
      );
      
      if (verification.status === "VERIFIED") {
        showStatus(
          "verifyStatus",
          "✅ VERIFICATION SUCCESSFUL! All data is authentic and untampered.",
          "success"
        );
      } else if (verification.status === "TAMPERED") {
        showStatus(
          "verifyStatus",
          "⚠️ TAMPERING DETECTED! The video or exam data has been modified.",
          "warning"
        );
      } else {
        showStatus("verifyStatus", "✅ Integrity check complete", "success");
      }
      
    } else {
      showStatus("verifyStatus", `❌ Verification failed: ${result.error}`, "error");
    }
    
  } catch (error) {
    showStatus("verifyStatus", `❌ Error: ${error.message}`, "error");
    console.error(error);
  }
}

// ========== SECTION 4: DECRYPTION ==========
async function decryptVideo() {
  if (!currentSessionId) {
    showStatus("decryptStatus", "❌ No session available. Complete previous sections first.", "error");
    return;
  }
  
  const sessionKey = document.getElementById("sessionKeyInput").value.trim();
  
  if (!sessionKey) {
    showStatus("decryptStatus", "❌ Please enter the session key", "error");
    return;
  }
  
  if (sessionKey.length !== 64) {
    showStatus(
      "decryptStatus",
      "❌ Invalid session key format (should be 64 hex characters for 256-bit key)",
      "error"
    );
    return;
  }
  
  showStatus("decryptStatus", "🔄 Decrypting video with AES-256-GCM...", "loading");
  
  try {
    const res = await fetch(`${API}/decrypt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionId: currentSessionId,
        sessionKey
      })
    });
    
    const result = await res.json();
    
    if (result.status === "success") {
      const displayData = {
        "Status": "✅ DECRYPTED",
        "Session ID": currentSessionId,
        "Decrypted File": result.decryptedFilename,
        "File Size (MB)": (result.size / 1024 / 1024).toFixed(2),
        "Algorithm": "AES-256-GCM",
        "Note": "Video decrypted successfully and saved on server. You can also download it."
      };
      
      document.getElementById("decryptOutput").textContent = JSON.stringify(
        displayData,
        null,
        2
      );
      showStatus("decryptStatus", "✅ Video decrypted successfully!", "success");
      
      // Optionally create download link
      if (result.decryptedData) {
        createDownloadButton(result.decryptedData, result.decryptedFilename);
      }
      
    } else {
      showStatus("decryptStatus", `❌ Decryption failed: ${result.error}`, "error");
    }
    
  } catch (error) {
    showStatus("decryptStatus", `❌ Error: ${error.message}`, "error");
    console.error(error);
  }
}

function createDownloadButton(base64Data, filename) {
  const decryptStatus = document.getElementById("decryptStatus");
  
  // Remove existing download button if any
  const existingBtn = document.getElementById("downloadBtn");
  if (existingBtn) existingBtn.remove();
  
  // Create download button
  const downloadBtn = document.createElement("button");
  downloadBtn.id = "downloadBtn";
  downloadBtn.className = "btn download-btn";
  downloadBtn.textContent = "💾 Download Decrypted Video";
  downloadBtn.style.marginTop = "15px";
  
  downloadBtn.onclick = () => {
    try {
      const byteString = atob(base64Data);
      const byteArray = new Uint8Array(byteString.length);
      for (let i = 0; i < byteString.length; i++) {
        byteArray[i] = byteString.charCodeAt(i);
      }
      const blob = new Blob([byteArray], { type: "video/webm" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      alert("Download failed: " + error.message);
    }
  };
  
  decryptStatus.parentElement.appendChild(downloadBtn);
}

// ========== HELPER FUNCTIONS ==========
function showStatus(elementId, message, type) {
  const statusBox = document.getElementById(elementId);
  statusBox.textContent = message;
  statusBox.className = `status-box ${type}`;
}

// ========== INITIALIZE ==========
window.addEventListener("DOMContentLoaded", () => {
  console.log("🔐 Exam Proctoring Security System Initialized");
  console.log("✅ AES-256-GCM Encryption Ready");
  console.log("✅ RSA-2048 Digital Signatures Ready");
  console.log("✅ SHA-256 Hashing Ready");
});
