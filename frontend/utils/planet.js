// 工具函数：计算花朵在星球表面的放置位置与法线
// 纯数学实现，便于在浏览器与 Node 测试中复用

export const defaultPlanetConfig = {
    radius: 30,
    scaleY: 0.1,
    center: { x: 0, y: -24, z: 0 },
    maxDistanceFactor: 0.9,
    // 将花朵整体上移的偏移量，便于让花朵更靠近星球顶部
    flowerYOffset: 0,
    // 为防止花朵被地表遮挡，额外向上浮动的高度
    flowerFloat: 0.5
};

/**
 * 计算在星球表面的坐标与法线
 * @param {{x:number, z:number}} basePosition 基础平面坐标（相对星球中心）
 * @param {{
 *  radius:number,
 *  scaleY:number,
 *  center:{x:number,y:number,z:number},
 *  maxDistanceFactor?:number
 * }} planetConfig 星球参数
 * @returns {{position:{x:number,y:number,z:number}, surfaceY:number, normal:{x:number,y:number,z:number}}}
 */
export function calculateSurfacePlacement(basePosition, planetConfig = defaultPlanetConfig) {
    const {
        radius,
        scaleY,
        center,
        maxDistanceFactor = 0.9,
        flowerYOffset = 0,
        flowerFloat = 0
    } = planetConfig;
    if (!basePosition || typeof basePosition.x !== 'number' || typeof basePosition.z !== 'number') {
        throw new Error('calculateSurfacePlacement 需要提供包含 x 和 z 的 basePosition');
    }

    const dx = basePosition.x - (center.x || 0);
    const dz = basePosition.z - (center.z || 0);
    const distanceFromCenter = Math.hypot(dx, dz);
    const clampedDistance = Math.min(distanceFromCenter, radius * maxDistanceFactor);
    const angle = Math.atan2(dz, dx);

    const surfaceX = Math.cos(angle) * clampedDistance + center.x;
    const surfaceZ = Math.sin(angle) * clampedDistance + center.z;

    // 原始球面高度（未压缩）
    let surfaceY = Math.sqrt(Math.max(0, radius * radius - clampedDistance * clampedDistance)) * scaleY;

    // 移除人工压扁逻辑，让花朵自然贴合表面
    // if (scaleY < 0.3) { ... }

    const normalVector = {
        x: surfaceX - center.x,
        y: surfaceY,
        z: surfaceZ - center.z
    };
    const normalLength = Math.hypot(normalVector.x, normalVector.y, normalVector.z) || 1;

    return {
        position: {
            x: surfaceX,
            y: center.y + surfaceY + flowerYOffset + flowerFloat,
            z: surfaceZ
        },
        surfaceY,
        normal: {
            x: normalVector.x / normalLength,
            y: normalVector.y / normalLength,
            z: normalVector.z / normalLength
        }
    };
}

