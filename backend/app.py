from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import json
import os
from datetime import datetime
from crypto_engine import (
    generate_session_key,
    compute_hash,
    encrypt_aes,
    decrypt_aes,
    generate_rsa_keys,
    sign_hash,
    verify_signature,
    serialize_public_key
)

app = Flask(__name__)
CORS(app)

# Generate RSA keys at startup
PRIVATE_KEY, PUBLIC_KEY = generate_rsa_keys()

# Storage directory for recordings
RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# In-memory storage for demo
sessions = {}

# ----------------- API ROUTES -----------------

@app.get("/")
def home():
    return jsonify({"status": "Backend running", "message": "OK"})


@app.get("/public-key")
def get_public_key():
    """Send public key to frontend for verification"""
    public_key_pem = serialize_public_key(PUBLIC_KEY)
    return jsonify({"publicKey": public_key_pem})


# ========== SECTION 1: EXAM SUBMISSION (Recording + Submit + AUTO ENCRYPT) ==========
@app.post("/start-exam")
def start_exam():
    """Initialize exam session"""
    data = request.get_json()
    session_id = data.get("sessionId")
    student_id = data.get("studentId")
    exam_id = data.get("examId")
    
    if not session_id or not student_id or not exam_id:
        return jsonify({"error": "Missing required fields"}), 400
    
    sessions[session_id] = {
        "studentId": student_id,
        "examId": exam_id,
        "startTime": datetime.now().isoformat(),
        "status": "in_progress"
    }
    
    return jsonify({
        "status": "success",
        "message": "Exam started",
        "sessionId": session_id
    })


@app.post("/submit-exam")
def submit_exam():
    """
    Submit exam with video recording.
    👉 This version automatically:
       - saves the video
       - computes SHA-256 hash
       - encrypts video with AES-256-GCM
       - signs exam data with RSA-PSS
       - returns all encryption details in one response
    """
    session_id = request.form.get("sessionId")
    video_file = request.files.get("video")
    exam_answers = request.form.get("examAnswers", "{}")
    
    if not session_id or not video_file:
        return jsonify({"error": "Missing session ID or video file"}), 400
    
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    # ---- 1. SAVE VIDEO ----
    filename = f"{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
    filepath = os.path.join(RECORDINGS_DIR, filename)
    video_file.save(filepath)
    
    # Read file and compute hash
    with open(filepath, 'rb') as f:
        file_bytes = f.read()
    
    file_hash = compute_hash(file_bytes)
    file_size = len(file_bytes)
    
    # Parse exam answers
    try:
        answers = json.loads(exam_answers)
    except Exception:
        answers = {}
    
    # Base session info
    sessions[session_id].update({
        "filename": filename,
        "filepath": filepath,
        "fileHash": file_hash,
        "fileSize": file_size,
        "examAnswers": answers,
        "endTime": datetime.now().isoformat()
    })
    
    # ---- 2. AUTO ENCRYPT VIDEO (AES-256-GCM) ----
    session_key = generate_session_key()  # 256-bit key in hex
    encrypted_video = encrypt_aes(file_bytes, session_key)
    
    encrypted_filename = f"encrypted_{filename}.enc"
    encrypted_filepath = os.path.join(RECORDINGS_DIR, encrypted_filename)
    
    encrypted_package = {
        "ciphertext": encrypted_video["ciphertext"],
        "iv": encrypted_video["iv"],
        "tag": encrypted_video["tag"]
    }
    
    with open(encrypted_filepath, 'w') as f:
        json.dump(encrypted_package, f)
    
    # ---- 3. SIGN EXAM DATA (RSA-PSS + SHA-256) ----
    exam_data = {
        "sessionId": session_id,
        "studentId": sessions[session_id]["studentId"],
        "examId": sessions[session_id]["examId"],
        "startTime": sessions[session_id]["startTime"],
        "endTime": sessions[session_id]["endTime"],
        "fileHash": file_hash,
        "fileSize": file_size,
        "examAnswers": answers
    }
    
    data_string = json.dumps(exam_data, indent=2)
    data_hash = compute_hash(data_string.encode("utf-8"))
    signature = sign_hash(PRIVATE_KEY, data_hash)
    
    # ---- 4. STORE FINAL CRYPTO STATE ----
    sessions[session_id].update({
        "status": "encrypted",
        "sessionKey": session_key,
        "encryptedFilepath": encrypted_filepath,
        "encryptedFilename": encrypted_filename,
        "iv": encrypted_video["iv"],
        "tag": encrypted_video["tag"],
        "ciphertextSize": len(encrypted_video["ciphertext"]),  # hex length
        "dataSignature": signature,
        "dataHash": data_hash,
        "examData": exam_data
    })
    
    # ---- 5. RETURN EVERYTHING TO FRONTEND ----
    return jsonify({
        "status": "success",
        "message": "Exam submitted and encrypted successfully",
        "sessionId": session_id,
        "filename": filename,
        "fileSize": file_size,
        "fileHash": file_hash,
        "encryption": {
            "sessionKey": session_key,
            "fileHash": file_hash,
            "dataHash": data_hash,
            "signature": signature,
            "iv": encrypted_video["iv"],
            "tag": encrypted_video["tag"],
            "ciphertextSize": len(encrypted_video["ciphertext"]),
            "encryptedFile": encrypted_filename,
            "algorithms": "AES-256-GCM + RSA-PSS + SHA-256"
        }
    })


# ========== SECTION 2: ENCRYPTION (OPTIONAL VIEW-ONLY ENDPOINT) ==========
@app.post("/encrypt")
def encrypt_data():
    """
    View encryption details.
    In AUTO mode, encryption already happened during /submit-exam.
    This endpoint just returns stored encryption info if available.
    """
    data = request.get_json()
    session_id = data.get("sessionId")
    
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    session = sessions[session_id]
    
    if session.get("status") != "encrypted":
        return jsonify({"error": "Exam not yet encrypted. Submit exam first."}), 400
    
    return jsonify({
        "status": "success",
        "message": "Encryption details",
        "data": {
            "sessionKey": session.get("sessionKey"),
            "fileHash": session.get("fileHash"),
            "dataHash": session.get("dataHash"),
            "dataSignature": session.get("dataSignature"),
            "iv": session.get("iv"),
            "tag": session.get("tag"),
            "encryptedFilename": session.get("encryptedFilename"),
            "encryptedSize": session.get("ciphertextSize"),
            "algorithms": "AES-256-GCM + RSA-PSS + SHA-256"
        }
    })


# ========== SECTION 4: DECRYPTION ==========
@app.post("/decrypt")
def decrypt_video():
    """Decrypt video using session key"""
    data = request.get_json()
    session_id = data.get("sessionId")
    session_key = data.get("sessionKey")
    
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    session = sessions[session_id]
    
    if session.get("status") != "encrypted":
        return jsonify({"error": "Video not encrypted yet"}), 400
    
    # Verify session key
    if session_key != session.get("sessionKey"):
        return jsonify({"error": "Invalid session key"}), 401
    
    try:
        # Read encrypted video
        with open(session["encryptedFilepath"], 'r') as f:
            encrypted_package = json.load(f)
        
        # Decrypt the video
        decrypted_bytes = decrypt_aes(encrypted_package, session_key)
        
        # Save decrypted video
        decrypted_filename = f"decrypted_{session['filename']}"
        decrypted_filepath = os.path.join(RECORDINGS_DIR, decrypted_filename)
        
        with open(decrypted_filepath, 'wb') as f:
            f.write(decrypted_bytes)
        
        # Convert to base64 for download
        decrypted_b64 = base64.b64encode(decrypted_bytes).decode()
        
        return jsonify({
            "status": "success",
            "message": "Video decrypted successfully",
            "decryptedFilename": decrypted_filename,
            "decryptedData": decrypted_b64,
            "size": len(decrypted_bytes)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== SECTION 3: TAMPER DETECTION ==========
@app.post("/verify-integrity")
def verify_integrity():
    """Verify video and exam data integrity"""
    data = request.get_json()
    session_id = data.get("sessionId")
    
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    session = sessions[session_id]
    
    if session.get("status") not in ["encrypted", "submitted"]:
        return jsonify({"error": "No data to verify"}), 400
    
    result = {
        "videoTampered": False,
        "dataTampered": False,
        "signatureValid": False,
        "status": "UNKNOWN"
    }
    
    try:
        # Check if video file exists and matches original hash
        if os.path.exists(session["filepath"]):
            with open(session["filepath"], 'rb') as f:
                current_bytes = f.read()
            
            current_hash = compute_hash(current_bytes)
            
            if current_hash != session["fileHash"]:
                result["videoTampered"] = True
        else:
            result["videoTampered"] = True
        
        # Verify exam data signature if encrypted
        if session.get("status") == "encrypted":
            # Recompute data hash
            data_string = json.dumps(session["examData"], indent=2)
            current_data_hash = compute_hash(data_string.encode('utf-8'))
            
            # Check if data hash matches
            if current_data_hash != session["dataHash"]:
                result["dataTampered"] = True
            
            # Verify RSA signature
            result["signatureValid"] = verify_signature(
                PUBLIC_KEY,
                session["dataSignature"],
                session["dataHash"]
            )
            
            if not result["signatureValid"]:
                result["dataTampered"] = True
        
        # Determine overall status
        if result["videoTampered"] or result["dataTampered"]:
            result["status"] = "TAMPERED"
        elif result["signatureValid"]:
            result["status"] = "VERIFIED"
        else:
            result["status"] = "VALID"
        
        return jsonify({
            "status": "success",
            "verification": result,
            "details": {
                "originalVideoHash": session["fileHash"],
                "originalDataHash": session.get("dataHash", "N/A"),
                "signaturePresent": "dataSignature" in session,
                "studentId": session["studentId"],
                "examId": session["examId"]
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/session/<session_id>")
def get_session(session_id):
    """Get session details"""
    if session_id in sessions:
        session_copy = sessions[session_id].copy()
        # Don't expose sensitive data
        if "sessionKey" in session_copy:
            session_copy["sessionKey"] = "***HIDDEN***"
        return jsonify({"status": "success", "session": session_copy})
    return jsonify({"error": "Session not found"}), 404


if __name__ == "__main__":
    print("=" * 70)
    print("🔐 EXAM PROCTORING SECURITY SYSTEM STARTED")
    print("=" * 70)
    print("📝 Section 1: Take Exam - Video recording during exam")
    print("🔒 Section 2: AUTO Encryption - AES-256-GCM + RSA-PSS signatures")
    print("🛡️ Section 3: Tamper Detection - Integrity verification")
    print("🔓 Section 4: Decryption - Secure video decryption")
    print("=" * 70)
    print(f"✅ RSA Keys Generated (2048-bit)")
    print(f"✅ AES-256 GCM Encryption Ready")
    print(f"✅ SHA-256 Hashing Active")
    print(f"✅ Recordings Directory: {RECORDINGS_DIR}")
    print("=" * 70)
    app.run(host="0.0.0.0", port=5002, debug=True)
