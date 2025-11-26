# Sonic Bloom - Cyber Garden 🌺

一个基于实时情绪、音频分析和手势交互的沉浸式 3D 花园可视化项目。通过摄像头捕捉面部表情和手势，通过麦克风分析声音特征，实时生成一个日式风格的 3D 花朵花园。

## ✨ 特性

### 🗣️ 语音交互生成 (Phase 1)
- **语音生成花朵**：对着麦克风说话，AI 会根据你的语音内容和情绪生成一朵独一无二的花朵。
- **小王子风格**：默认生成风格独特的"小王子"星球花朵。
- **实时转写**：集成语音转文字功能，理解你的意图。

### 🦋 手势控制蝴蝶 (Phase 2)
- **21点骨架追踪**：使用 MediaPipe Hands 实时追踪手部 21 个关键点。
- **区域控制飞行**：
  - **👆 UP**：手在屏幕上方 -> 蝴蝶向上飞
  - **👇 DOWN**：手在屏幕下方 -> 蝴蝶向下飞
  - **👈 LEFT**：手在屏幕左侧 -> 蝴蝶向左飞
  - **👉 RIGHT**：手在屏幕右侧 -> 蝴蝶向右飞
  - **✋ CENTER**：手在屏幕中央 -> 蝴蝶悬停
- **👌 捏合互动**：识别拇指和食指的捏合手势，触发特殊互动（如吸引蝴蝶）。
- **可视化反馈**：屏幕实时显示手部骨架和控制区域。

### 🎭 情绪识别
- 使用 **DeepFace** 实时分析面部表情
- 支持 7 种情绪：开心、悲伤、愤怒、惊讶、恐惧、厌恶、中性
- 情绪稳定算法，避免快速跳变
- 情绪映射到花朵颜色（日式低饱和度配色）

### 🔊 音频分析
- **响度分析**：使用 librosa 计算音频 RMS，控制花朵大小
- **音高分析**：使用 librosa.pyin 提取基频（F0），控制花朵旋转
- 实时音频处理和平滑过渡

### 🤖 AI 智能系统（可选）
- **AgentScope 多智能体系统**：
  - **VisualDesignerAgent**：使用大模型智能推荐视觉参数（颜色、光照、粒子效果）
  - **ButterflyControllerAgent**：AI 控制蝴蝶行为逻辑（飞行路径、互动模式）
  - **EnvironmentGeneratorAgent**：动态生成环境效果（光照、雾效、氛围）
  - **CoordinatorAgent**：协调所有智能体，整合结果
- 支持 **DeepSeek** 和 **阿里云百炼平台** API

### 🎨 高级视觉效果
- **Three.js** 3D 渲染引擎
- **Post-processing 效果**：SSAO、Bloom、Film Grain
- **GPU 加速粒子系统**：10,000+ 粒子
- **自定义 Shader Material**：花瓣发光和脉动效果
- 日式低饱和度配色方案

## 🏗️ 项目结构

```
cyberFamer/
├── backend/              # Python/FastAPI 后端
│   ├── main.py          # 主应用文件（FastAPI + WebSocket）
│   ├── agents/          # AI 智能体模块
│   └── ...
├── frontend/            # JavaScript/Three.js 前端
│   ├── index.html       # HTML 入口文件
│   ├── main.js          # Three.js 场景和逻辑
│   ├── ml/              # 机器学习模块
│   │   ├── pose-detection.js    # MediaPipe Hands 封装
│   │   └── gesture-recognizer.js # 手势识别逻辑
│   ├── models/          # 3D 模型 (Butterfly)
│   ├── ai/              # AI 系统
│   └── ...
└── README.md            # 项目文档
```

## 🛠️ 技术栈

### 后端
- **Python 3.12+**
- **FastAPI** - Web 框架和 WebSocket 服务器
- **DeepFace** - 面部情绪识别
- **OpenCV** - 摄像头捕获
- **librosa** - 音频分析
- **AgentScope** - 多智能体框架

### 前端
- **Three.js** - 3D 渲染引擎
- **TensorFlow.js** & **MediaPipe Hands** - 手势识别
- **Post-processing** - 后处理效果
- **WebSocket** - 实时数据通信

## 📦 安装步骤

### 前置要求
1. **Python 3.12+**
2. **uv** (Python 包管理器)
3. **portaudio** (音频库)

### 安装依赖
```bash
cd cyberFamer/backend
uv sync
```

### 配置 API Keys（可选）
复制 `.env.example` 为 `.env` 并填入 `DEEPSEEK_API_KEY` 或 `DASHSCOPE_API_KEY` 以启用 AI 功能。

## 🚀 运行步骤

### 1. 启动后端
```bash
cd backend
uv run python main.py
```

### 2. 启动前端
```bash
cd frontend
python -m http.server 8080
```
访问 `http://localhost:8080`

## 🎮 交互指南

### 第一阶段：语音生成 (Voice Interaction)
1.  点击屏幕上的 **"🎤 Start Recording"** 按钮。
2.  对着麦克风说一句话（例如："今天天气真好"）。
3.  再次点击按钮停止录音。
4.  系统会分析你的语音和情绪，生成一朵专属的花朵。

### 第二阶段：手势控制 (Gesture Interaction)
1.  花朵生成后，系统会自动切换到手势控制模式。
2.  举起一只手，确保摄像头能看到你的手掌。
3.  **控制蝴蝶飞行**：
    *   手在**上方**区域 -> 蝴蝶向上飞
    *   手在**下方**区域 -> 蝴蝶向下飞
    *   手在**左侧**区域 -> 蝴蝶向左飞
    *   手在**右侧**区域 -> 蝴蝶向右飞
4.  **特殊互动**：
    *   **捏合 (Pinch)**：拇指和食指捏合，触发特殊效果。

## 📝 开发计划

- [x] AI 智能体系统集成
- [x] 语音交互生成花朵
- [x] 21点手部骨架追踪
- [x] 交互式蝴蝶系统 (区域控制)
- [x] GPU 粒子系统
- [x] 高级后处理效果
- [ ] 添加多人模式支持
- [ ] 增加更多花朵类型和样式
- [ ] 移动端适配

## 📄 许可证

本项目为课程作业项目，仅供学习和研究使用。

---

**享受你的 Cyber Garden 之旅！** 🌸✨
