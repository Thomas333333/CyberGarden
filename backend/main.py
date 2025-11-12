import asyncio
import cv2
import numpy as np
import librosa
import pyaudio
import json
import time
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from deepface import DeepFace
import uvicorn

# --- FastAPI App ---
app = FastAPI()

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# WebSocket 路由
@app.websocket("/ws/data")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接，等待后端推送数据
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- 情绪稳定性处理 ---
class EmotionStabilizer:
    def __init__(self, window_size=10, threshold=0.6, min_confidence=0.35):
        self.emotion_history = deque(maxlen=window_size)
        self.current_emotion = "neutral"
        self.confidence_threshold = threshold
        self.min_confidence = min_confidence
    
    def update(self, emotion, confidence=None):
        """更新情绪，返回稳定后的情绪"""
        if confidence is not None and confidence < self.min_confidence:
            # 低置信度时跳过更新，避免频繁跳变
            return self.current_emotion

        self.emotion_history.append(emotion)
        
        # 统计最近的情绪分布
        emotion_counts = {}
        for e in self.emotion_history:
            emotion_counts[e] = emotion_counts.get(e, 0) + 1
        
        # 找到最常见的情绪
        if emotion_counts:
            most_common = max(emotion_counts.items(), key=lambda x: x[1])
            emotion_freq = most_common[1] / len(self.emotion_history)
            
            # 只有当情绪频率超过阈值时才更新
            if emotion_freq >= self.confidence_threshold:
                self.current_emotion = most_common[0]
        
        return self.current_emotion

emotion_stabilizer = EmotionStabilizer(window_size=12, threshold=0.5, min_confidence=0.4)

# --- TEST ONLY: 全局共享帧和情绪数据（用于调试摄像头叠加显示） ---
latest_frame = None
latest_emotion_snapshot = {
    "raw_emotion": "neutral",
    "raw_confidence": 0.0,
    "raw_face_detected": False,
    "stable_face_detected": False,
    "loudness": 0.0,
    "pitch": 220.0,
}
_face_presence_score = 0.0

# --- 音频和视频分析 ---
async def analyze_media():
    # 初始化摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Warning: Could not open camera")
        return
    
    # 设置摄像头分辨率（提高检测精度）
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # 初始化音频
    CHUNK = 2048  # 增加块大小以提高音高检测精度
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("Starting media analysis...")
    
    # 音频平滑处理
    loudness_history = deque(maxlen=5)
    pitch_history = deque(maxlen=5)
    
    global latest_frame, latest_emotion_snapshot, _face_presence_score

    try:
        frame_count = 0
        while True:
            # 1. 读取视频帧（降低帧率以减少计算负担）
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1)
                continue
            
            frame_count += 1
            analysis_frame = frame.copy()
            
            # 2. 读取音频块
            audio_data = stream.read(CHUNK, exception_on_overflow=False)
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # 3. 分析情绪（降低检测频率）
            raw_emotion = latest_emotion_snapshot.get("raw_emotion", "neutral")
            confidence = latest_emotion_snapshot.get("confidence", 0.0)
            raw_confidence = latest_emotion_snapshot.get("raw_confidence", 0.0)
            raw_face_detected = latest_emotion_snapshot.get("raw_face_detected", False)
            stable_face_detected = latest_emotion_snapshot.get("stable_face_detected", False)
            detection_updated = False
            if frame_count % 3 == 0:  # 每3帧检测一次
                try:
                    # 缩小图像以提高速度
                    small_frame = cv2.resize(analysis_frame, (320, 240))
                    rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    
                    result = DeepFace.analyze(
                        rgb_frame,
                        actions=['emotion'],
                        detector_backend='opencv',
                        enforce_detection=False,
                        silent=True
                    )
                    if isinstance(result, list):
                        result = result[0]
                    
                    # 获取情绪和置信度
                    emotion_scores = result.get('emotion', {})
                    if emotion_scores:
                        raw_emotion, raw_confidence_score = max(emotion_scores.items(), key=lambda x: x[1])
                        raw_confidence = float(raw_confidence_score) / 100.0
                    else:
                        raw_emotion = result.get('dominant_emotion', 'neutral')
                        raw_confidence = float(result.get('face_confidence', 0.0))
                        if raw_confidence > 1:
                            raw_confidence /= 100.0
                    
                    face_conf = float(result.get('face_confidence', 0.0))
                    if face_conf > 1:
                        face_conf = face_conf / 100.0
                    raw_face_detected = (face_conf >= 0.4) or (raw_confidence >= 0.4)
                    detection_updated = True

                    if raw_face_detected:
                        emotion_stabilizer.update(raw_emotion, raw_confidence)
                        confidence = float(max(raw_confidence, face_conf))
                    else:
                        confidence = 0.0
                    
                except Exception as e:
                    # 只在出错时打印，避免刷屏
                    if frame_count % 30 == 0:
                        print(f"Emotion analysis error: {e}")
            
            # 4. 分析响度 (RMS) - 平滑处理
            try:
                rms = librosa.feature.rms(y=audio_array, frame_length=CHUNK)[0][0]
                loudness = float(np.clip(rms * 15, 0, 1))  # 调整归一化
                loudness_history.append(loudness)
                loudness = float(np.mean(loudness_history))  # 使用平均值
            except Exception as e:
                loudness = 0.0
            
            # 5. 分析音高 (F0) - 平滑处理
            try:
                f0, voiced_flag, voiced_probs = librosa.pyin(
                    audio_array,
                    fmin=50,
                    fmax=400,
                    sr=RATE,
                    frame_length=CHUNK
                )
                valid_f0 = f0[~np.isnan(f0)]
                if len(valid_f0) > 0:
                    pitch = float(np.median(valid_f0))  # 使用中位数更稳定
                    pitch = np.clip(pitch, 50, 400)
                else:
                    pitch = 220.0
                
                pitch_history.append(pitch)
                pitch = float(np.mean(pitch_history))  # 使用平均值
            except Exception as e:
                pitch = 220.0
            
            # 6. 格式化数据为 JSON
            data = {
                "emotion": raw_emotion,
                "raw_emotion": raw_emotion,
                "raw_confidence": float(raw_confidence),
                "loudness": float(loudness),
                "pitch": float(pitch)
            }
            json_data = json.dumps(data)
            
            # 7. 广播数据（降低频率）
            if manager.active_connections:
                await manager.broadcast(json_data)
            
            # --- TEST ONLY: 保存最新帧与情绪快照用于视频调试 ---
            latest_frame = frame.copy()
            if detection_updated:
                target = 1.0 if raw_face_detected else 0.0
                _face_presence_score = (_face_presence_score * 0.65) + (target * 0.35)
            else:
                _face_presence_score = (_face_presence_score * 0.98)
            _face_presence_score = max(0.0, min(1.0, _face_presence_score))
            stable_face_detected = _face_presence_score >= 0.4

            latest_emotion_snapshot = {
                "raw_emotion": raw_emotion,
                "raw_confidence": raw_confidence,
                "confidence": confidence,
                "raw_face_detected": raw_face_detected,
                "stable_face_detected": stable_face_detected,
                "loudness": loudness,
                "pitch": pitch,
            }

            # 8. 控制更新频率
            await asyncio.sleep(0.15)  # 降低更新频率
            
    except Exception as e:
        print(f"Analysis error: {e}")
    finally:
        cap.release()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        print("Media analysis stopped")

# --- 启动任务 ---
@app.on_event("startup")
async def startup_event():
    # 启动后台分析任务
    asyncio.create_task(analyze_media())


# --- TEST ONLY: 后端摄像头调试流（带情绪信息叠加） ---
def generate_test_video_stream():
    """MJPEG 生成器，用于测试摄像头画面与情绪识别结果"""
    boundary = b'--frame'
    while True:
        if latest_frame is None:
            time.sleep(0.05)
            continue

        frame = latest_frame.copy()
        snapshot = latest_emotion_snapshot.copy()

        overlay_lines = [
            f"Raw Emotion: {snapshot['raw_emotion']}",
            f"Raw Conf: {snapshot['raw_confidence']:.2f}",
            f"Raw Face: {snapshot['raw_face_detected']}",
            f"Stable Face: {snapshot['stable_face_detected']}",
            f"Loudness: {snapshot['loudness']:.2f}",
            f"Pitch: {snapshot['pitch']:.1f} Hz",
        ]
        y_offset = 30
        for line in overlay_lines:
            cv2.putText(
                frame,
                line,
                (20, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 170),
                2,
                cv2.LINE_AA
            )
            y_offset += 28

        success, buffer = cv2.imencode('.jpg', frame)
        if not success:
            time.sleep(0.05)
            continue

        frame_bytes = buffer.tobytes()
        yield (
            boundary + b'\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
        )


@app.get("/video")
def video_stream_with_emotion_overlay():
    """
    TEST ONLY: 调试接口，返回带情绪信息叠加的摄像头视频流。
    前端可用于快速验证情绪识别结果与画面同步情况。
    """
    return StreamingResponse(
        generate_test_video_stream(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
