# Sonic Bloom - Cyber Garden 🌺

An immersive 3D garden visualization project based on real-time emotion, audio analysis, and gesture interaction. Through camera capture of facial expressions and gestures, and microphone analysis of audio features, it generates a Japanese-style 3D flower garden in real-time.

## ✨ Features

### 🗣️ Voice Interaction Generation (Phase 1)
- **Voice-Generated Flowers**: Speak into the microphone, and AI will generate a unique flower based on your voice content and emotions.
- **Little Prince Style**: Default generation style features unique "Little Prince" planet flowers.
- **Real-time Transcription**: Integrated speech-to-text functionality to understand your intent.

### 🦋 Gesture-Controlled Butterfly (Phase 2)
- **21-Point Skeleton Tracking**: Uses MediaPipe Hands to track 21 hand keypoints in real-time.
- **Zone-Based Flight Control**:
  - **👆 UP**: Hand in upper screen area -> Butterfly flies upward
  - **👇 DOWN**: Hand in lower screen area -> Butterfly flies downward
  - **👈 LEFT**: Hand in left screen area -> Butterfly flies left
  - **👉 RIGHT**: Hand in right screen area -> Butterfly flies right
  - **✋ CENTER**: Hand in center screen area -> Butterfly hovers
- **👌 Pinch Interaction**: Recognizes thumb and index finger pinch gestures to trigger special interactions (e.g., attracting butterflies).
- **Visual Feedback**: Real-time display of hand skeleton and control zones on screen.

### 🎭 Emotion Recognition
- Uses **DeepFace** for real-time facial expression analysis
- Supports 7 emotions: happy, sad, angry, surprised, fearful, disgusted, neutral
- Emotion stabilization algorithm to avoid rapid fluctuations
- Emotion mapping to flower colors (Japanese low-saturation color scheme)

### 🔊 Audio Analysis
- **Loudness Analysis**: Uses librosa to calculate audio RMS, controlling flower size
- **Pitch Analysis**: Uses librosa.pyin to extract fundamental frequency (F0), controlling flower rotation
- Real-time audio processing and smooth transitions

### 🤖 AI Intelligent System (Optional)
- **AgentScope Multi-Agent System**:
  - **VisualDesignerAgent**: Uses large language models to intelligently recommend visual parameters (colors, lighting, particle effects)
  - **ButterflyControllerAgent**: AI controls butterfly behavior logic (flight paths, interaction modes)
  - **EnvironmentGeneratorAgent**: Dynamically generates environmental effects (lighting, fog, atmosphere)
  - **CoordinatorAgent**: Coordinates all agents and integrates results
- Supports **DeepSeek** and **Alibaba Cloud DashScope** APIs

### 🎨 Advanced Visual Effects
- **Three.js** 3D rendering engine
- **Post-processing Effects**: SSAO, Bloom, Film Grain
- **GPU-Accelerated Particle System**: 10,000+ particles
- **Custom Shader Material**: Petal glow and pulsation effects
- Japanese low-saturation color scheme

## 🏗️ Project Structure

```
cyberFamer/
├── backend/              # Python/FastAPI Backend
│   ├── main.py          # Main application file (FastAPI + WebSocket)
│   ├── agents/          # AI agent modules
│   └── ...
├── frontend/            # JavaScript/Three.js Frontend
│   ├── index.html       # HTML entry file
│   ├── main.js          # Three.js scene and logic
│   ├── ml/              # Machine learning modules
│   │   ├── pose-detection.js    # MediaPipe Hands wrapper
│   │   └── gesture-recognizer.js # Gesture recognition logic
│   ├── models/          # 3D models (Butterfly)
│   ├── ai/              # AI system
│   └── ...
└── README.md            # Project documentation
```

## 🛠️ Tech Stack

### Backend
- **Python 3.12+**
- **FastAPI** - Web framework and WebSocket server
- **DeepFace** - Facial emotion recognition
- **OpenCV** - Camera capture
- **librosa** - Audio analysis
- **AgentScope** - Multi-agent framework

### Frontend
- **Three.js** - 3D rendering engine
- **TensorFlow.js** & **MediaPipe Hands** - Gesture recognition
- **Post-processing** - Post-processing effects
- **WebSocket** - Real-time data communication

## 📦 Installation

### Prerequisites
1. **Python 3.12+**
2. **uv** (Python package manager)
3. **portaudio** (Audio library)

### Install Dependencies
```bash
cd cyberFamer/backend
uv sync
```

### Configure API Keys (Optional)
Copy `.env.example` to `.env` and fill in `DEEPSEEK_API_KEY` or `DASHSCOPE_API_KEY` to enable AI features.

## 🚀 Running the Project

### 1. Start Backend
```bash
cd backend
uv run python main.py
```

### 2. Start Frontend
```bash
cd frontend
python -m http.server 8080
```
Visit `http://localhost:8080`

## 🎮 Interaction Guide

### Phase 1: Voice Generation (Voice Interaction)
1. Click the **"🎤 Start Recording"** button on the screen.
2. Speak into the microphone (e.g., "The weather is nice today").
3. Click the button again to stop recording.
4. The system will analyze your voice and emotions to generate a unique flower.

### Phase 2: Gesture Control (Gesture Interaction)
1. After the flower is generated, the system automatically switches to gesture control mode.
2. Raise one hand, ensuring the camera can see your palm.
3. **Control Butterfly Flight**:
   * Hand in **upper** area -> Butterfly flies upward
   * Hand in **lower** area -> Butterfly flies downward
   * Hand in **left** area -> Butterfly flies left
   * Hand in **right** area -> Butterfly flies right
4. **Special Interactions**:
   * **Pinch**: Thumb and index finger pinch to trigger special effects.

## 📝 Development Roadmap

- [x] AI agent system integration
- [x] Voice interaction flower generation
- [x] 21-point hand skeleton tracking
- [x] Interactive butterfly system (zone control)
- [x] GPU particle system
- [x] Advanced post-processing effects
- [ ] Add multi-user mode support
- [ ] Add more flower types and styles
- [ ] Mobile device adaptation

## 📄 License

This project is a course assignment project, for learning and research purposes only.

---

**Enjoy your Cyber Garden journey!** 🌸✨
