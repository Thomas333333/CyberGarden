import asyncio
import numpy as np
import librosa
import pyaudio
import json
import os
import tempfile
from collections import deque
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
import assemblyai as aai

# 加载 .env 文件
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 初始化 AssemblyAI
# 支持两种环境变量名称：ASSEMBLY_API_KEY 和 Assembly_API_KEY
assembly_api_key = os.getenv("ASSEMBLY_API_KEY") or os.getenv("Assembly_API_KEY") or ""
if assembly_api_key:
    aai.settings.api_key = assembly_api_key
    print("✓ AssemblyAI API key loaded")
else:
    print("⚠ Warning: ASSEMBLY_API_KEY or Assembly_API_KEY not found in .env")

# AgentScope imports
from agentscope.model import OpenAIChatModel, DashScopeChatModel
from agents.visual_designer import VisualDesignerAgent
from agents.butterfly_controller import ButterflyControllerAgent
from agents.environment_generator import EnvironmentGeneratorAgent
from agents.coordinator import CoordinatorAgent
import ast

# --- FastAPI App ---
app = FastAPI()

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AgentScope 初始化 ---
def extract_json_robust(text: str) -> dict:
    """
    终极 JSON 提取器 v3 (自动拆包版)：
    1. 优先提取 Markdown 代码块
    2. 递归寻找最外层 {} 或 []
    3. 尝试多种解析方式 (json, ast)
    4. [新增] 自动拆包：如果解析结果是 DashScope/AgentScope 的包装器，自动提取内部 text 再解析
    """
    if not text:
        raise ValueError("Empty text provided")

    # --- 内部函数：基础解析逻辑 ---
    def _parse_candidate(candidate_text):
        # 1. 尝试标准 JSON
        try:
            return json.loads(candidate_text)
        except:
            pass
        # 2. 尝试清洗换行符后 JSON
        try:
            cleaned = candidate_text.replace("\\n", "\n").replace("\\t", "\t")
            return json.loads(cleaned)
        except:
            pass
        # 3. 尝试 Python AST (处理单引号)
        try:
            return ast.literal_eval(candidate_text)
        except:
            pass
        # 4. 尝试暴力修复
        try:
            fixed = candidate_text.replace("'", '"')
            fixed = fixed.replace("None", "null").replace("True", "true").replace("False", "false")
            return json.loads(fixed)
        except:
            pass
        return None

    # --- 主流程 ---
    
    # 1. 预处理
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)
    code_block = re.search(r'```(?:json)?\s*([\{\[][\s\S]*?[\]\}])\s*```', text, re.IGNORECASE)
    if code_block:
        text = code_block.group(1)

    # 2. 寻找最外层的结构 ({...} 或 [...])
    # 有时候 wrapper 是 list: [{'text': ...}]
    start_brace = text.find('{')
    start_bracket = text.find('[')
    
    start_idx = -1
    end_idx = -1
    
    # 确定是找 { 还是找 [
    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        start_idx = start_brace
        end_idx = text.rfind('}')
    elif start_bracket != -1:
        start_idx = start_bracket
        end_idx = text.rfind(']')
        
    if start_idx == -1 or end_idx == -1:
        # 如果找不到外层结构，尝试直接解析整个文本（可能是裸字符串）
        candidate = text
    else:
        candidate = text[start_idx : end_idx + 1]

    # 3. 执行初次解析
    result = _parse_candidate(candidate)
    
    if result is None:
        raise ValueError(f"Could not parse JSON. Content: {text[:50]}...")

    # --- [关键修复] 递归拆包逻辑 ---
    # 检查是否是 DashScope/AgentScope 的包装器结构
    
    # 情况 A: 列表包装 [{'type': 'text', 'text': '{...}'}]
    if isinstance(result, list) and len(result) > 0:
        item = result[0]
        if isinstance(item, dict) and 'text' in item:
            print("📦 Detected List Wrapper, unboxing...")
            return extract_json_robust(item['text']) # 递归调用
            
    # 情况 B: 字典包装 {'type': 'text', 'text': '{...}'}
    if isinstance(result, dict):
        # 如果包含 'text' 且不包含我们需要的业务字段（比如 'analysis' 或 'size'），说明它可能只是个包装
        # 这里做一个简单的判断：如果 'text' 的值看起来像 JSON 字符串（以 { 开头），就钻进去
        if 'text' in result and isinstance(result['text'], str):
            inner_text = result['text'].strip()
            if inner_text.startswith('{') or inner_text.startswith('['):
                print("📦 Detected Dict Wrapper, unboxing...")
                return extract_json_robust(inner_text) # 递归调用

    return result
def init_agents():
    """初始化 AgentScope 和 agents"""
    try:
        # 创建模型实例
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        
        deepseek_model = None
        if deepseek_api_key:
            try:
                deepseek_model = OpenAIChatModel(
                    model_name="deepseek-chat",
                    api_key=deepseek_api_key,
                    base_url="https://api.deepseek.com"
                )
            except Exception as e:
                print(f"Error creating DeepSeek model: {e}")
        
        qwen_model = None
        if dashscope_api_key:
            try:
                qwen_model = DashScopeChatModel(
                    model_name="qwen-turbo",
                    api_key=dashscope_api_key
                )
            except Exception as e:
                print(f"Error creating DashScope model: {e}")
        
        # 创建 agents（如果 API key 不存在，使用 None，agent 会使用默认值）
        primary_model = deepseek_model if deepseek_model else qwen_model
        
        if not primary_model:
            print("❌ 错误: 没有可用的 AI 模型 (DeepSeek 和 DashScope Key 都缺失)")
            return None

        # 4. 创建 Agents
        # Visual Agent (首选 DeepSeek)
        visual_model = deepseek_model if deepseek_model else primary_model
        visual_agent = VisualDesignerAgent(
            name="VisualDesigner",
            model=visual_model
        )
        print(f"VisualAgent 创建成功 (使用: {visual_model.model_name if hasattr(visual_model, 'model_name') else 'Unknown'})")
        
        # Butterfly Agent (首选 Qwen)
        butterfly_model = qwen_model if qwen_model else primary_model
        butterfly_agent = ButterflyControllerAgent(
            name="ButterflyController",
            model=butterfly_model
        )
        print(f"ButterflyAgent 创建成功 (使用: {butterfly_model.model_name if hasattr(butterfly_model, 'model_name') else 'Unknown'})")
        
        # Environment Agent (首选 DeepSeek)
        env_model = deepseek_model if deepseek_model else primary_model
        env_agent = EnvironmentGeneratorAgent(
            name="EnvironmentGenerator",
            model=env_model
        )
        print(f"EnvironmentAgent 创建成功 (使用: {env_model.model_name if hasattr(env_model, 'model_name') else 'Unknown'})")
        
        # 创建协调者
        if visual_agent and butterfly_agent and env_agent:
            coordinator = CoordinatorAgent(
                visual_agent=visual_agent,
                butterfly_agent=butterfly_agent,
                env_agent=env_agent
            )
            print("AgentScope initialized successfully")
            return coordinator
        else:
            print("Warning: Some API keys are missing. Agents will use default values.")
            return None
            
    except Exception as e:
        print(f"Error initializing AgentScope: {e}")
        print("Continuing without AI agents...")
        return None

# 初始化 agents
coordinator = init_agents()

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✓ WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"✗ WebSocket disconnected. Remaining connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # 创建连接列表的副本，避免在迭代时修改列表
        connections_to_remove = []
        for connection in self.active_connections:
            try:
                # 检查连接状态
                if connection.client_state.name == "CONNECTED":
                    await connection.send_text(message)
                else:
                    connections_to_remove.append(connection)
            except Exception as e:
                # 连接已断开，标记为需要移除
                print(f"Error sending message to WebSocket: {e}")
                connections_to_remove.append(connection)
        
        # 移除断开的连接
        for connection in connections_to_remove:
            self.disconnect(connection)

manager = ConnectionManager()

# --- 语音转文本和花朵参数生成 ---
async def transcribe_audio(audio_file_path: str) -> str:
    """使用 AssemblyAI 将音频文件转换为文本"""
    try:
        if not assembly_api_key:
            raise ValueError("AssemblyAI API key not configured")
        
        config = aai.TranscriptionConfig(
            speech_model=aai.SpeechModel.best,
            language_code="en"  # 可以根据需要修改
        )
        
        transcriber = aai.Transcriber(config=config)
        
        # transcribe 方法是同步的，会阻塞直到转录完成
        # 在异步函数中，我们需要在线程池中运行它以避免阻塞事件循环
        import asyncio
        loop = asyncio.get_event_loop()
        
        print(f"Starting transcription for: {audio_file_path}")
        transcript = await loop.run_in_executor(None, transcriber.transcribe, audio_file_path)
        print(f"Transcription completed. Status: {transcript.status}")
        
        # 检查转录状态
        if transcript.status == aai.TranscriptStatus.error:
            error_msg = getattr(transcript, 'error', 'Unknown error')
            raise RuntimeError(f"Transcription failed: {error_msg}")
        
        # 确保转录成功
        if transcript.status != aai.TranscriptStatus.completed:
            raise RuntimeError(f"Transcription status: {transcript.status}, expected completed")
        
        # 获取转录文本
        text = transcript.text
        if not text:
            raise RuntimeError("Transcription completed but no text returned")
        
        print(f"Transcription text: {text[:100]}...")  # 打印前100个字符
        return text
    except Exception as e:
        print(f"Error in transcription: {e}")
        import traceback
        traceback.print_exc()
        raise

import inspect
import json
import re
async def generate_flower_params_from_text(text: str, coordinator_instance=None) -> dict:
    """
    扁平版花朵参数生成：
    - 模型返回一个扁平 JSON，无 parameters 嵌套
    - 自动收集流式/非流式 chunk
    - 自动解析 JSON（使用 extract_json_robust）
    - 失败回退 simple 规则
    """

    print(f"--- 扁平版生成花朵参数: '{text}' ---")

    try:
        # 1. 没有 agent → fallback
        if not coordinator_instance or not getattr(coordinator_instance, "visual_agent", None):
            print("⚠️ Agent 未初始化，使用 simple 规则。")
            return generate_flower_params_simple(text)

        # ------------------------------------------------
        # 2. Stage 1: Generate Parameters (JSON)
        # ------------------------------------------------
        prompt_stage1 = f"""
You are a 'Digital Gardener'.
User said: "{text}"

Generate flower parameters in strict JSON format:
{{
  "size": number(0.8-2.0),
  "color": "#hex",
  "petalCount": int(3-12),
  "brightness": number(0.3-2.0),
  "emotion": "emotion_tag",
  "rotation_speed": number(0.0-0.05)
}}
Only output the JSON object. No markdown, no explanations.
"""
        print("🤖 Stage 1: Generating parameters...")
        response1 = await coordinator_instance.visual_agent.model(
            messages=[{"role": "user", "content": prompt_stage1}]
        )
        
        # Helper to collect text (improved for DashScope incremental output)
        import inspect
        import re
        import json
        import ast

        # async def collect_text(resp):
        #     """
        #     智能流式收集器：自动识别 Delta(增量) 和 Accumulation(全量) 模式
        #     """
        #     full_text = ""
        #     last_chunk_text = "" # 记录上一帧的纯文本内容，用于判断模式
            
        #     if inspect.isasyncgen(resp):
        #         async for chunk in resp:
        #             content = ""
                    
        #             # 1. 提取当前帧的文本内容
        #             if isinstance(chunk, dict):
        #                 content = chunk.get("text", "") or chunk.get("content", "")
        #             elif hasattr(chunk, "text"): # DashScope response object
        #                 content = chunk.text
        #             elif hasattr(chunk, "content"): # OpenAI delta object
        #                 content = chunk.content
        #             else:
        #                 content = str(chunk)
                        
        #             if not content:
        #                 continue

        #             content_str = str(content)

        #             # 2. 智能判断模式
        #             # 如果当前帧包含上一帧的内容（且长度更长），说明是全量更新（DashScope/Qwen模式）
        #             # 我们取前10个字符做快速模糊匹配，避免开头有细微差别导致判断失败
        #             check_len = min(len(last_chunk_text), 20)
        #             is_accumulation = False
                    
        #             if check_len > 0 and content_str.startswith(last_chunk_text[:check_len]):
        #                 is_accumulation = True
        #             elif len(content_str) > len(last_chunk_text) and last_chunk_text in content_str:
        #                 is_accumulation = True

        #             # 3. 更新 full_text
        #             if is_accumulation:
        #                 # 全量模式：直接覆盖
        #                 full_text = content_str
        #             else:
        #                 # 增量模式：追加 (OpenAI模式)
        #                 # 注意：如果全量模式判断失败，可能会导致重复，这里加一个额外保险
        #                 # 如果追加的内容和结尾重复，则不追加
        #                 if not full_text.endswith(content_str):
        #                     full_text += content_str
                    
        #             last_chunk_text = content_str # 更新上一帧记录
                    
        #     else:
        #         # 非流式处理
        #         if isinstance(resp, dict):
        #             if "text" in resp: full_text = str(resp["text"])
        #             elif "content" in resp: full_text = str(resp["content"])
        #             else: full_text = str(resp)
        #         elif hasattr(resp, "text") and resp.text: full_text = str(resp.text)
        #         elif hasattr(resp, "content") and resp.content: full_text = str(resp.content)
        #         else: full_text = str(resp)

        #     # 4. 清理 DashScope 可能残留的 artifact
        #     if "'type': 'text'" in full_text:
        #         try:
        #             # 尝试提取 Python 字典字符串形式的 text 字段
        #             matches = re.findall(r"'text':\s*'([^']*)'", full_text)
        #             if matches:
        #                 # 取最长的一个，通常是最终结果
        #                 full_text = max(matches, key=len)
        #         except:
        #             pass
                    
        #     return full_text

        async def collect_text(resp):
            """
            collect_text V3 (安全版):
            1. 移除了导致截断的危险正则清理逻辑。
            2. 保留了智能的全量/增量识别。
            """
            full_text = ""
            last_chunk_text = "" 
            
            if inspect.isasyncgen(resp):
                async for chunk in resp:
                    content = ""
                    
                    # 1. 提取当前帧的文本内容
                    if isinstance(chunk, dict):
                        content = chunk.get("text", "") or chunk.get("content", "")
                    elif hasattr(chunk, "text"): 
                        content = chunk.text
                    elif hasattr(chunk, "content"): 
                        content = chunk.content
                    else:
                        content = str(chunk)
                        
                    if not content:
                        continue

                    content_str = str(content)

                    # 2. 智能判断模式 (全量 vs 增量)
                    check_len = min(len(last_chunk_text), 20)
                    is_accumulation = False
                    
                    # 只有当 current 比 full 长，或者 current 包含 full 的前缀时
                    if check_len > 0 and content_str.startswith(last_chunk_text[:check_len]):
                        is_accumulation = True
                    elif len(content_str) > len(last_chunk_text) and last_chunk_text in content_str:
                        is_accumulation = True

                    # 3. 更新 full_text
                    if is_accumulation:
                        full_text = content_str
                    else:
                        # 增量模式：追加
                        if not full_text.endswith(content_str):
                            full_text += content_str
                    
                    last_chunk_text = content_str 
                    
            else:
                # 非流式处理
                if isinstance(resp, dict):
                    if "text" in resp: full_text = str(resp["text"])
                    elif "content" in resp: full_text = str(resp["content"])
                    else: full_text = str(resp)
                elif hasattr(resp, "text") and resp.text: full_text = str(resp.text)
                elif hasattr(resp, "content") and resp.content: full_text = str(resp.content)
                else: full_text = str(resp)

            # 4. [已删除危险的正则清理]
            # 这里的正则 '([^']*)' 会在遇到英文撇号(如 user's)时截断文本，
            # extract_json_robust 中的 ast.literal_eval 已经足够处理 Python 风格的字典字符串。
            
            return full_text
    
        text1 = await collect_text(response1)
        print(f"📦 Stage 1 Output: {text1}")
        params = extract_json_robust(text1)
        print("✅ Stage 1 JSON parsed:", params)

        # ------------------------------------------------
        # 3. Stage 2: Generate Analysis (Text)
        # ------------------------------------------------
        prompt_stage2 = f"""
User said: "{text}"
Flower parameters generated: {json.dumps(params)}

Task:
1. "analysis": Poetically interpret the user's input in ENGLISH (max 40 words).
2. "connection": Explain why these parameters (color {params.get('color')}, emotion {params.get('emotion')}) were chosen in ENGLISH (max 30 words).

Output strict JSON:
{{
  "analysis": "...",
  "connection": "..."
}}
"""
        print("🤖 Stage 2: Generating analysis...")
        response2 = await coordinator_instance.visual_agent.model(
            messages=[{"role": "user", "content": prompt_stage2}]
        )
        
        text2 = await collect_text(response2)
        print(f"📦 Stage 2 Output: {text2}")
        analysis_data = extract_json_robust(text2)
        print("✅ Stage 2 JSON parsed:", analysis_data)

        # ------------------------------------------------
        # 4. Combine Results
        # ------------------------------------------------
        final_result = {**params, **analysis_data}
        
        # Validation
        required_fields = ["analysis", "connection", "size", "color", "petalCount", "brightness", "emotion", "rotation_speed"]
        for field in required_fields:
            if field not in final_result:
                print(f"⚠️ Missing field {field}, using simple fallback")
                return generate_flower_params_simple(text)

        final_result["input_text"] = text
        return final_result

    except Exception as e:
        print(f"❌ Two-stage process failed: {e}")
        print("🔁 Using simple fallback")
        return generate_flower_params_simple(text)


def generate_flower_params_simple(text: str) -> dict:
    """简单的基于关键词的花朵参数生成（备用方案）"""
    text_lower = text.lower()
    
    # 颜色映射
    color_map = {
        "happy": "#FFD700", "good": "#FFD700", "great": "#FFD700", "wonderful": "#FFD700",
        "sad": "#4169E1", "bad": "#4169E1", "tired": "#4169E1", "down": "#4169E1",
        "excited": "#FF1493", "amazing": "#FF1493", "awesome": "#FF1493",
        "calm": "#90EE90", "peaceful": "#90EE90", "relaxed": "#90EE90",
        "angry": "#FF4500", "frustrated": "#FF4500", "mad": "#FF4500",
        "love": "#FF69B4", "loved": "#FF69B4", "caring": "#FF69B4"
    }
    
    # 大小映射
    size = 1.0
    if any(word in text_lower for word in ["big", "large", "huge", "amazing"]):
        size = 1.3
    elif any(word in text_lower for word in ["small", "little", "tiny"]):
        size = 0.7
    
    # 检测情绪
    emotion = "neutral"
    for emo, words in [
        ("happy", ["happy", "good", "great", "wonderful", "nice"]),
        ("sad", ["sad", "bad", "tired", "down", "difficult"]),
        ("excited", ["excited", "amazing", "awesome", "fantastic"]),
        ("calm", ["calm", "peaceful", "relaxed", "quiet"]),
        ("angry", ["angry", "frustrated", "mad", "annoyed"]),
        ("love", ["love", "loved", "caring", "warm"])
    ]:
        if any(word in text_lower for word in words):
            emotion = emo
            break
    
    # 选择颜色
    color = color_map.get(emotion, "#FFD700")
    
    return {
        "input_text": text,
        "analysis": f"Detected emotion: {emotion}.",
        "connection": f"Generated a {color} flower to represent your {emotion} mood.",
        "size": size,
        "color": color,
        "petalCount": 6,
        "brightness": 0.8 if emotion in ["happy", "excited", "love"] else 0.6,
        "emotion": emotion,
        "rotation_speed": 0.02
    }

# --- API 路由 ---
@app.post("/api/transcribe")
async def transcribe_audio_endpoint(audio: UploadFile = File(...)):
    """接收音频文件并转换为文本"""
    tmp_path = None
    try:
        # 获取文件扩展名
        filename = audio.filename or "audio"
        file_ext = os.path.splitext(filename)[1] or ".webm"
        
        print(f"Received audio file: {filename}, content_type: {audio.content_type}")
        
        # 保存临时文件（保持原始格式，AssemblyAI 支持多种格式）
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            content = await audio.read()
            file_size = len(content)
            print(f"Audio file size: {file_size} bytes")
            
            if file_size == 0:
                raise ValueError("Audio file is empty")
            
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        print(f"Saved audio file to: {tmp_path}")
        
        # 转录音频
        text = await transcribe_audio(tmp_path)
        
        # 清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                print(f"Cleaned up temporary file: {tmp_path}")
            except Exception as cleanup_error:
                print(f"Warning: Failed to cleanup temp file: {cleanup_error}")
        
        return JSONResponse({
            "success": True,
            "text": text
        })
    except Exception as e:
        # 确保清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
        
        error_msg = str(e)
        print(f"✗ Error in transcription endpoint: {error_msg}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse({
            "success": False,
            "error": error_msg
        }, status_code=500)

@app.post("/api/generate-flower-params")
async def generate_flower_params_endpoint(request: dict):
    """根据文本生成花朵参数"""
    try:
        text = request.get("text", "")
        if not text:
            raise ValueError("Text is required")
        
        params = await generate_flower_params_from_text(text, coordinator)
        
        return JSONResponse({
            "success": True,
            "params": params
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

# WebSocket 路由
@app.websocket("/ws/data")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print(f"✓ WebSocket connected. Total connections: {len(manager.active_connections)}")
    try:
        while True:
            # 接收前端发送的数据（如姿态数据）
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    received_data = json.loads(data)
                    if received_data.get("type") == "pose":
                        # 更新全局姿态数据（在 analyze_media 中使用）
                        # 注意：这里需要线程安全的方式传递数据
                        pass
                    elif received_data.get("type") == "ping":
                        # 响应前端心跳
                        await websocket.send_text(json.dumps({"type": "pong", "timestamp": received_data.get("timestamp")}))
                except Exception as e:
                    print(f"Error processing received data: {e}")
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"✗ WebSocket disconnected. Remaining connections: {len(manager.active_connections)}")

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
async def analyze_media(coordinator_instance=None):
    # 初始化摄像头
    # Camera disabled in backend to avoid conflict with frontend.
    print("Camera disabled in backend to avoid conflict with frontend.")
    
    # 初始化音频（添加错误处理）
    CHUNK = 2048  # 增加块大小以提高音高检测精度
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    
    audio = None
    stream = None
    
    try:
        audio = pyaudio.PyAudio()
        
        # 列出可用的音频输入设备（调试用）
        print("Available audio input devices:")
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  Device {i}: {info['name']} (inputs: {info['maxInputChannels']})")
        
        # 尝试打开默认输入设备
        try:
            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=None,  # 使用默认设备
                start=False  # 先不启动，避免权限问题
            )
            stream.start_stream()
            print("Audio stream opened successfully")
        except OSError as e:
            print(f"Warning: Could not open audio stream: {e}")
            print("Audio analysis will be disabled. Please check microphone permissions.")
            # 清理资源
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
            if audio:
                try:
                    audio.terminate()
                except:
                    pass
            audio = None
            stream = None
    except Exception as e:
        print(f"Warning: Audio initialization failed: {e}")
        print("Audio analysis will be disabled.")
        audio = None
        stream = None
    
    print("Starting media analysis...")
    
    # 音频平滑处理
    loudness_history = deque(maxlen=5)
    pitch_history = deque(maxlen=5)
    
    # 花朵位置（用于蝴蝶行为）
    flower_positions = [
        {"x": -4, "y": 0, "z": -3},
        {"x": -2, "y": 0, "z": -4},
        {"x": 0, "y": 0, "z": -4},
        {"x": 2, "y": 0, "z": -3},
        {"x": 4, "y": 0, "z": -2},
        {"x": -3, "y": 0, "z": 2},
        {"x": 0, "y": 0, "z": 3},
        {"x": 3, "y": 0, "z": 2},
        {"x": -5, "y": 0, "z": 0},
        {"x": 5, "y": 0, "z": 0},
        {"x": 0, "y": 0, "z": 0},  # 中心花朵
    ]
    
    # 姿态数据（暂时为空，后续由前端提供）
    pose_data = None
    
    try:
        frame_count = 0
        emotion_duration = 0
        last_emotion = "neutral"
        emotion = "neutral"
        confidence = 0.5  # 默认置信度
        
        while True:
            # 1. 读取视频帧（已禁用）
            # if cap:
            #     ret, frame = cap.read()
            #     if not ret:
            #         await asyncio.sleep(0.1)
            #         continue
            # else:
            #     # 如果没有摄像头，使用空白帧
            #     frame = np.zeros((480, 640, 3), dtype=np.uint8)
            #     await asyncio.sleep(0.1)
            
            frame_count += 1
            # analysis_frame = frame.copy()
            
            # 2. 读取音频块（如果音频流可用）
            if stream and stream.is_active():
                try:
                    audio_data = stream.read(CHUNK, exception_on_overflow=False)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                except Exception as e:
                    if frame_count % 30 == 0:  # 每30帧打印一次错误
                        print(f"Audio read error: {e}")
                    audio_array = np.zeros(CHUNK, dtype=np.float32)
            else:
                # 如果没有音频流，使用静音
                audio_array = np.zeros(CHUNK, dtype=np.float32)
            
            # 3. 分析情绪（已禁用后端视觉情绪分析）
            # 默认情绪为 neutral，或者等待前端发送情绪数据（如果需要）
            emotion = "neutral"
            confidence = 0.5
            
            # raw_emotion = latest_emotion_snapshot.get("raw_emotion", "neutral")
            # confidence = latest_emotion_snapshot.get("confidence", 0.0)
            # raw_confidence = latest_emotion_snapshot.get("raw_confidence", 0.0)
            # raw_face_detected = latest_emotion_snapshot.get("raw_face_detected", False)
            # stable_face_detected = latest_emotion_snapshot.get("stable_face_detected", False)
            # detection_updated = False
            # if frame_count % 3 == 0:  # 每3帧检测一次
            #     try:
            #         # 缩小图像以提高速度
            #         small_frame = cv2.resize(analysis_frame, (320, 240))
            #         rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            #         
            #         result = DeepFace.analyze(
            #             rgb_frame,
            #             actions=['emotion'],
            #             detector_backend='opencv',
            #             enforce_detection=False,
            #             silent=True
            #         )
            #         if isinstance(result, list):
            #             result = result[0]
            #         
            #         # 获取情绪和置信度
            #         emotion_scores = result.get('emotion', {})
            #         if emotion_scores:
            #             emotion = max(emotion_scores.items(), key=lambda x: x[1])[0]
            #             confidence = emotion_scores.get(emotion, 0) / 100.0
            #         else:
            #             emotion = result.get('dominant_emotion', 'neutral')
            #             confidence = 0.5
            #         
            #         # 使用稳定器平滑情绪
            #         emotion = emotion_stabilizer.update(emotion, confidence)
            #         
            #         # 计算情绪持续时间
            #         if emotion == last_emotion:
            #             emotion_duration += 0.15
            #         else:
            #             emotion_duration = 0.15
            #             last_emotion = emotion
            #         
            #     except Exception as e:
            #         # 只在出错时打印，避免刷屏
            #         if frame_count % 30 == 0:
            #             print(f"Emotion analysis error: {e}")
            
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
            
            # 6. 调用 AI agents（每10帧调用一次，降低API调用频率）
            ai_data = None
            if coordinator_instance and frame_count % 10 == 0:
                try:
                    emotion_intensity = confidence * 10
                    audio_features = {
                        "loudness": loudness,
                        "pitch": pitch
                    }
                    
                    ai_data = await coordinator_instance.process_emotion_data(
                        emotion=emotion,
                        emotion_intensity=emotion_intensity,
                        audio_features=audio_features,
                        pose_data=pose_data,
                        flower_positions=flower_positions
                    )
                except Exception as e:
                    print(f"Error calling agents: {e}")
                    ai_data = None
            
            # 7. 格式化数据为 JSON
            data = {
                "emotion": emotion,
                "loudness": loudness,
                "pitch": pitch,
                "emotion_intensity": confidence * 10,
                "emotion_duration": emotion_duration
            }
            
            # 添加 AI 推荐数据
            if ai_data:
                data["ai"] = {
                    "visual": ai_data.get("visual"),
                    "butterfly": ai_data.get("butterfly"),
                    "environment": ai_data.get("environment")
                }
            
            json_data = json.dumps(data, default=str)
            
            # 8. 广播数据（降低频率）
            if manager.active_connections:
                await manager.broadcast(json_data)
                # 每30帧打印一次日志，确认数据正在发送
                if frame_count % 30 == 0:
                    print(f"[{frame_count}] 已发送数据: emotion={emotion}, loudness={loudness:.2f}, pitch={pitch:.1f}, connections={len(manager.active_connections)}")
            else:
                # 如果没有连接，每30帧打印一次警告
                if frame_count % 30 == 0:
                    # print(f"[{frame_count}] 警告: 没有活跃的WebSocket连接")
                    pass
            
            # 9. 控制更新频率
            await asyncio.sleep(0.15)  # 降低更新频率
            
    except Exception as e:
        print(f"Analysis error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        # if cap:
        #     cap.release()
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception as e:
                print(f"Error closing audio stream: {e}")
        if audio:
            try:
                audio.terminate()
            except Exception as e:
                print(f"Error terminating audio: {e}")
        print("Media analysis stopped")

# --- 启动任务 ---
@app.on_event("startup")
async def startup_event():
    # 启动后台分析任务，传入 coordinator
    asyncio.create_task(analyze_media(coordinator))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
