import json
import os
import tempfile
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request
from openai import OpenAI
import requests

# 같은 폴더의 api_keys.env 파일 로드
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "api_keys.env"))

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>음성 명령 내비게이션</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
      background: #f3f5f8;
      color: #1f2937;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 20px;
    }
    .card {
      width: 100%;
      max-width: 480px;
      background: #ffffff;
      border-radius: 20px;
      padding: 28px 24px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 22px;
      font-weight: 700;
    }
    .desc {
      margin: 0 0 22px;
      font-size: 14px;
      color: #6b7280;
      line-height: 1.5;
    }
    .btn-area {
      display: flex;
      gap: 10px;
      margin-bottom: 18px;
    }
    button {
      flex: 1;
      padding: 14px 16px;
      font-size: 15px;
      font-weight: 600;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      transition: transform 0.08s ease, opacity 0.2s ease;
    }
    button:active { transform: scale(0.99); }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    #btn-record {
      background: #2563eb;
      color: #ffffff;
    }
    #btn-record.recording {
      background: #dc2626;
    }
    #btn-tmap {
      background: #10b981;
      color: #ffffff;
      display: none;
    }
    .status {
      padding: 12px 14px;
      border-radius: 10px;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      font-size: 14px;
      margin-bottom: 16px;
      min-height: 44px;
      display: flex;
      align-items: center;
    }
    .status.error {
      background: #fef2f2;
      border-color: #fecaca;
      color: #b91c1c;
    }
    .result-box {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 16px;
      display: none;
    }
    .result-row {
      margin-bottom: 10px;
      font-size: 14px;
      line-height: 1.45;
    }
    .result-row:last-child { margin-bottom: 0; }
    .label {
      font-weight: 700;
      color: #374151;
      display: inline-block;
      min-width: 78px;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>음성 내비게이션</h1>
    <p class="desc">말하기 버튼을 누르고 <strong>"서울역으로 가자"</strong>처럼 목적지를 말씀해 주세요.</p>

    <div class="btn-area">
      <button id="btn-record" type="button">말하기</button>
      <button id="btn-tmap" type="button">TMAP 가기</button>
    </div>

    <div id="status" class="status">대기 중입니다. 말하기 버튼을 눌러주세요.</div>

    <div id="result-box" class="result-box">
      <div class="result-row"><span class="label">인식 음성:</span><span id="transcript">-</span></div>
      <div class="result-row"><span class="label">목적지:</span><span id="place-name">-</span></div>
      <div class="result-row"><span class="label">주소:</span><span id="address">-</span></div>
      <div class="result-row"><span class="label">좌표:</span><span id="coords">-</span></div>
    </div>
  </div>

  <script>
    const btnRecord = document.getElementById("btn-record");
    const btnTmap = document.getElementById("btn-tmap");
    const statusEl = document.getElementById("status");
    const resultBox = document.getElementById("result-box");

    const transcriptEl = document.getElementById("transcript");
    const placeNameEl = document.getElementById("place-name");
    const addressEl = document.getElementById("address");
    const coordsEl = document.getElementById("coords");

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let selectedDestination = null;

    function setStatus(msg, isError = false) {
      statusEl.textContent = msg;
      statusEl.classList.toggle("error", isError);
    }

    function resetDestination() {
      selectedDestination = null;
      btnTmap.style.display = "none";
      resultBox.style.display = "none";
    }

    async function startRecording() {
      resetDestination();
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunks.push(event.data);
          }
        };

        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
          await sendAudioToServer(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        btnRecord.textContent = "말하기 종료";
        btnRecord.classList.add("recording");
        setStatus("음성을 듣고 있습니다... 말씀을 마치면 버튼을 다시 누르세요.");
      } catch (err) {
        setStatus("마이크 접근에 실패했습니다. 마이크 권한을 확인하고 다시 말해 주세요.", true);
      }
    }

    function stopRecording() {
      if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        btnRecord.textContent = "말하기";
        btnRecord.classList.remove("recording");
        btnRecord.disabled = true;
        setStatus("음성을 분석하고 목적지를 찾는 중입니다...");
      }
    }

    async function sendAudioToServer(blob) {
      const formData = new FormData();
      formData.append("audio", blob, "voice.webm");

      try {
        const res = await fetch("/api/voice-navigation", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
          setStatus(data.message || "음성인식이나 목적지 확인에 실패했습니다. 다시 말해 주세요.", true);
          return;
        }

        selectedDestination = data.destination;
        resultBox.style.display = "block";
        transcriptEl.textContent = data.transcript;
        placeNameEl.textContent = selectedDestination.name;
        addressEl.textContent = selectedDestination.road_address || selectedDestination.address || "-";
        coordsEl.textContent = `위도 ${selectedDestination.lat}, 경도 ${selectedDestination.lng}`;

        btnTmap.style.display = "inline-block";
        setStatus(`"${selectedDestination.name}" 목적지를 찾았습니다. TMAP 가기 버튼을 누르세요.`);
      } catch (err) {
        setStatus("서버 통신 중 오류가 발생했습니다. 다시 말해 주세요.", true);
      } finally {
        btnRecord.disabled = false;
      }
    }

    btnRecord.addEventListener("click", () => {
      if (!isRecording) {
        startRecording();
      } else {
        stopRecording();
      }
    });

    btnTmap.addEventListener("click", () => {
      if (!selectedDestination) {
        setStatus("전달할 목적지 정보가 없습니다. 다시 말해 주세요.", true);
        return;
      }
      const goalName = encodeURIComponent(selectedDestination.name);
      const goalX = encodeURIComponent(selectedDestination.lng); // 경도
      const goalY = encodeURIComponent(selectedDestination.lat); // 위도

      const tmapUrl = `tmap://route?goalx=${goalX}&goaly=${goalY}&goalname=${goalName}`;
      window.location.href = tmapUrl;
      setStatus(`TMAP으로 "${selectedDestination.name}" 목적지 정보를 전달했습니다.`);
    });
  </script>
</body>
</html>
"""


def transcribe_audio(file_path: str) -> str:
    """음성 파일을 텍스트로 변환(STT)"""
    if not client:
        raise RuntimeError("api_keys.env의 OPENAI_API_KEY가 설정되지 않았습니다.")

    with open(file_path, "rb") as audio_file:
        resp = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file,
            language="ko",
        )
    return (resp.text or "").strip()


def extract_destination(transcript: str) -> str | None:
    """GPT API를 통해 발화 텍스트에서 목적지 명칭 추출"""
    if not client or not transcript:
        return None

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "너는 운전자의 음성 명령에서 목적지 장소명만 추출하는 도우미다. "
                    "명확한 목적지(장소, 건물, 역, 지역 등)가 있으면 {\"destination\": \"목적지명\"} 형태로 반환하고, "
                    "목적지가 불분명하거나 없다면 {\"destination\": null} 형태로 반환하라."
                ),
            },
            {"role": "user", "content": transcript},
        ],
    )
    raw = completion.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    dest = parsed.get("destination")
    if isinstance(dest, str) and dest.strip():
        return dest.strip()
    return None


def search_kakao_place(query: str) -> dict | None:
    """Kakao Local API 키워드 검색으로 위도/경도 조회"""
    if not KAKAO_REST_API_KEY:
        raise RuntimeError("api_keys.env의 KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": query, "size": 1}

    resp = requests.get(url, headers=headers, params=params, timeout=8)
    resp.raise_for_status()
    documents = resp.json().get("documents", [])
    if not documents:
        return None

    top = documents[0]
    return {
        "name": top.get("place_name") or query,
        "address": top.get("address_name", ""),
        "road_address": top.get("road_address_name", ""),
        "lat": float(top["y"]),  # 위도
        "lng": float(top["x"]),  # 경도
    }


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/voice-navigation", methods=["POST"])
def voice_navigation():
    if "audio" not in request.files:
        return jsonify({"ok": False, "message": "음성 파일이 수신되지 않았습니다. 다시 말해 주세요."}), 400

    audio_file = request.files["audio"]
    suffix = os.path.splitext(audio_file.filename or "voice.webm")[1] or ".webm"
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        transcript = transcribe_audio(tmp_path)
        if not transcript:
            return jsonify({
                "ok": False,
                "message": "음성인식에 실패했습니다. 다시 말해 주세요."
            }), 200

        destination_query = extract_destination(transcript)
        if not destination_query:
            return jsonify({
                "ok": False,
                "transcript": transcript,
                "message": f'"{transcript}"에서 목적지를 확인할 수 없습니다. 다시 말해 주세요.'
            }), 200

        place = search_kakao_place(destination_query)
        if not place:
            return jsonify({
                "ok": False,
                "transcript": transcript,
                "message": f'"{destination_query}" 위치를 찾을 수 없습니다. 다시 말해 주세요.'
            }), 200

        return jsonify({
            "ok": True,
            "transcript": transcript,
            "destination": place,
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "message": f"처리 중 오류가 발생했습니다({e}). 다시 말해 주세요."
        }), 500

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
