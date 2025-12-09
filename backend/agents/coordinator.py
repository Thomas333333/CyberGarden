# """
# Coordinator Agent
# 协调所有 agents 的工作，整合结果
# """

# import asyncio
# from typing import Dict, Optional


# class CoordinatorAgent:
#     """协调者智能体 - 协调所有 agents 的工作"""
    
#     def __init__(self, visual_agent, butterfly_agent, env_agent, **kwargs):
#         self.name = "Coordinator"
#         self.visual_agent = visual_agent
#         self.butterfly_agent = butterfly_agent
#         self.env_agent = env_agent
    
#     async def process_emotion_data(
#         self,
#         emotion: str,
#         emotion_intensity: float,
#         audio_features: Dict,
#         pose_data: Optional[Dict] = None,
#         flower_positions: Optional[list] = None
#     ) -> Dict:
#         """协调处理情绪数据，返回整合后的结果"""
        
#         # 并行调用各个 agents
#         tasks = [
#             self.visual_agent.recommend_visual_params(emotion, emotion_intensity, pose_data),
#             self.butterfly_agent.decide_behavior(emotion, emotion_intensity, pose_data, flower_positions),
#             self.env_agent.generate_environment(emotion, emotion_intensity, pose_data.get('motion_level', 0) if pose_data else 0)
#         ]
        
#         try:
#             results = await asyncio.gather(*tasks, return_exceptions=True)
            
#             visual_params = results[0] if not isinstance(results[0], Exception) else None
#             butterfly_behavior = results[1] if not isinstance(results[1], Exception) else None
#             env_params = results[2] if not isinstance(results[2], Exception) else None
            
#             # 整合结果
#             return {
#                 'visual': visual_params,
#                 'butterfly': butterfly_behavior,
#                 'environment': env_params,
#                 'emotion': emotion,
#                 'emotion_intensity': emotion_intensity,
#                 'audio': audio_features
#             }
#         except Exception as e:
#             print(f"Error in coordinator: {e}")
#             # 返回基础结果
#             return {
#                 'visual': None,
#                 'butterfly': None,
#                 'environment': None,
#                 'emotion': emotion,
#                 'emotion_intensity': emotion_intensity,
#                 'audio': audio_features
#             }

import json
import asyncio
import re
import inspect
from typing import Dict, Any, Optional

class CoordinatorAgent:
    def __init__(self, visual_agent, butterfly_agent, env_agent, **kwargs):
        self.visual_agent = visual_agent
        self.butterfly_agent = butterfly_agent
        self.env_agent = env_agent

    async def _extract_content(self, response) -> str:
        """通用辅助函数：修复版，支持字典 key 为 'text' 的情况"""
        raw_content = ""
        
        if inspect.isasyncgen(response):
            async for chunk in response:
                val = None
                # 优先检查对象属性
                if hasattr(chunk, 'content'): val = chunk.content
                elif hasattr(chunk, 'text'): val = chunk.text
                
                # 检查字典 (你的报错就是因为缺少对 'text' key 的检查)
                elif isinstance(chunk, dict):
                    if 'text' in chunk: val = chunk['text']       # <--- 新增
                    elif 'content' in chunk: val = chunk['content']
                
                # 检查字符串
                elif isinstance(chunk, str): val = chunk
                
                if val:
                    if isinstance(val, str): raw_content += val
                    elif isinstance(val, list): raw_content += "".join([str(v) for v in val])
        else:
            # 非流式
            val = None
            if hasattr(response, 'content'): val = response.content
            elif hasattr(response, 'text'): val = response.text
            else: val = str(response)
            
            if val:
                if isinstance(val, str): raw_content += val
                elif isinstance(val, list): raw_content += "".join([str(v) for v in val])
                
        return raw_content

    async def _parse_json_from_response(self, response, context_tag="unknown") -> Optional[Dict]:
        """通用 JSON 解析器"""
        try:
            text = await self._extract_content(response)
            # 简单的正则匹配 JSON
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            # 静默失败，避免刷屏，仅打印关键信息
            # print(f"Error parsing {context_tag}: {e}") 
            return None

    async def process_emotion_data(self, emotion: str, emotion_intensity: float, 
                                 audio_features: Dict, pose_data: Optional[Dict] = None, 
                                 flower_positions: Optional[list] = None) -> Dict:
        """
        协调处理情绪数据，直接调用模型以确保解析可控
        """
        # 基础上下文
        base_context = f"Emotion: {emotion}, Intensity: {emotion_intensity}, Pitch: {audio_features.get('pitch', 0)}"

        # 构造 Prompts
        visual_prompt = f"Context: {base_context}. Task: Adjust visuals. Output JSON: {{ \"bloom_intensity\": 0.0-1.0, \"color\": {{ \"r\": 0-1, \"g\": 0-1, \"b\": 0-1 }} }}"
        butterfly_prompt = f"Context: {base_context}. Task: Butterfly behavior. Output JSON: {{ \"flight_speed\": 0.1-2.0, \"attraction_strength\": 0.0-1.0 }}"
        env_prompt = f"Context: {base_context}. Task: Environment fog. Output JSON: {{ \"fog\": {{ \"enabled\": true, \"density\": 0.0-0.05, \"color\": {{ \"r\":0, \"g\":0, \"b\":0 }} }} }}"

        try:
            # 并发调用模型
            responses = await asyncio.gather(
                self.visual_agent.model(messages=[{"role": "user", "content": visual_prompt}]),
                self.butterfly_agent.model(messages=[{"role": "user", "content": butterfly_prompt}]),
                self.env_agent.model(messages=[{"role": "user", "content": env_prompt}]),
                return_exceptions=True
            )

            # 解析结果
            visual_res = responses[0] if not isinstance(responses[0], Exception) else None
            butterfly_res = responses[1] if not isinstance(responses[1], Exception) else None
            env_res = responses[2] if not isinstance(responses[2], Exception) else None

            visual_data = await self._parse_json_from_response(visual_res, "visual")
            butterfly_data = await self._parse_json_from_response(butterfly_res, "butterfly")
            env_data = await self._parse_json_from_response(env_res, "environment")

            return {
                "visual": visual_data or {},
                "butterfly": butterfly_data or {},
                "environment": env_data or {},
                "emotion": emotion
            }

        except Exception as e:
            print(f"Coordinator Loop Error: {e}")
            return {}