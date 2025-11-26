/**
 * Pose Detection Module
 * 使用 TensorFlow.js Hand Pose Detection 进行实时手势检测 (21点骨架)
 */

class PoseDetector {
    constructor() {
        this.detector = null;
        this.video = null;
        this.isDetecting = false;
        this.currentHands = null; // Changed from currentPose
        this.handPosition = null;
        this.callbacks = [];
    }

    async init() {
        try {
            console.log('开始初始化手势检测器 (Hand Pose Detection)...');

            // 检查全局变量
            if (typeof window.tf === 'undefined') {
                throw new Error('TensorFlow.js 未加载');
            }
            if (typeof window.handPoseDetection === 'undefined') {
                throw new Error('Hand Pose Detection 未加载');
            }

            await window.tf.ready();
            console.log('✓ TensorFlow.js 后端已就绪');

            // 设置后端
            try {
                await window.tf.setBackend('webgl');
                console.log('✓ 使用 WebGL 后端');
            } catch (e) {
                console.warn('WebGL 不可用，使用默认后端:', e);
            }

            const model = window.handPoseDetection.SupportedModels.MediaPipeHands;
            const detectorConfig = {
                runtime: 'mediapipe', // 或者 'tfjs'
                solutionPath: 'https://cdn.jsdelivr.net/npm/@mediapipe/hands',
                modelType: 'full',
                maxHands: 2
            };

            this.detector = await window.handPoseDetection.createDetector(model, detectorConfig);
            console.log('✓ Hand Pose detector 初始化成功');
            return true;

        } catch (error) {
            console.error('✗ Error initializing hand pose detector:', error);
            return false;
        }
    }

    async startDetection(videoElement) {
        try {
            if (!this.detector) {
                const initialized = await this.init();
                if (!initialized) return false;
            }

            if (!videoElement) return false;

            this.video = videoElement;
            this.isDetecting = true;
            console.log('✓ 开始手势检测循环');
            this.detectLoop();
            return true;
        } catch (error) {
            console.error('✗ 启动检测失败:', error);
            return false;
        }
    }

    stopDetection() {
        this.isDetecting = false;
    }

    async detectLoop() {
        if (!this.isDetecting || !this.detector || !this.video) return;

        try {
            // estimateHands 返回手部数组
            const hands = await this.detector.estimateHands(this.video, {
                flipHorizontal: false // 我们在CSS中翻转了视频，这里不需要翻转
            });

            if (hands && hands.length > 0) {
                this.currentHands = hands;
                this.extractHandPosition(hands);
                this.notifyCallbacks(hands, this.handPosition);
            } else {
                this.currentHands = null;
                this.handPosition = null;
                this.notifyCallbacks(null, null);
            }
        } catch (error) {
            console.error('Hand detection error:', error);
        }

        if (this.isDetecting) {
            requestAnimationFrame(() => this.detectLoop());
        }
    }

    extractHandPosition(hands) {
        if (!hands || hands.length === 0) {
            this.handPosition = null;
            return;
        }

        // 优先选择置信度高的手
        const hand = hands.reduce((prev, current) => (prev.score > current.score) ? prev : current);

        if (hand && hand.keypoints) {
            // 获取手腕位置作为主要位置
            // keypoints[0] 是 wrist
            const wrist = hand.keypoints[0];

            // 归一化坐标转换 (假设视频分辨率 640x480)
            const videoWidth = this.video.videoWidth || 640;
            const videoHeight = this.video.videoHeight || 480;

            const normalizedX = wrist.x / videoWidth;
            const normalizedY = wrist.y / videoHeight;

            // 转换为 3D 空间坐标 (-10 到 10)
            const x = (normalizedX - 0.5) * 20;
            const y = (0.5 - normalizedY) * 15;

            // 简单的深度估计 (基于手的大小或特定点距离，这里简化为0)
            const z = 0;

            this.handPosition = {
                x: x,
                y: y + 2,
                z: z,
                confidence: hand.score,
                normalizedX: normalizedX,
                normalizedY: normalizedY,
                handedness: hand.handedness // 'Left' or 'Right'
            };
        } else {
            this.handPosition = null;
        }
    }

    onPoseDetected(callback) {
        this.callbacks.push(callback);
    }

    notifyCallbacks(hands, handPos) {
        this.callbacks.forEach(callback => {
            try {
                callback(hands, handPos);
            } catch (error) {
                console.error('Callback error:', error);
            }
        });
    }
}

export { PoseDetector };

