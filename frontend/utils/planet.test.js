import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateSurfacePlacement, defaultPlanetConfig } from './planet.js';

const approxEqual = (a, b, tolerance = 1e-6) => Math.abs(a - b) <= tolerance;

test('使用 scaleY 压扁后，顶部花朵高度等于中心高度 + radius*scaleY', () => {
    const placement = calculateSurfacePlacement({ x: 5, z: -5 }, defaultPlanetConfig);
    const expectedY =
        defaultPlanetConfig.center.y +
        defaultPlanetConfig.radius * defaultPlanetConfig.scaleY +
        defaultPlanetConfig.flowerYOffset +
        defaultPlanetConfig.flowerFloat;

    assert.ok(approxEqual(placement.position.y, expectedY), `期望高度 ${expectedY}，得到 ${placement.position.y}`);
    assert.ok(placement.normal.y > 0.3, '顶部位置的法线应明显指向上方');
});

test('距离超过限制时会按 maxDistanceFactor 夹紧并保持高度压缩', () => {
    const placement = calculateSurfacePlacement({ x: 100, z: 0 }, defaultPlanetConfig);
    const maxDistance = defaultPlanetConfig.radius * defaultPlanetConfig.maxDistanceFactor;
    const distance = Math.hypot(placement.position.x - defaultPlanetConfig.center.x, placement.position.z - defaultPlanetConfig.center.z);

    assert.ok(approxEqual(distance, maxDistance), `距离未按预期夹紧到 ${maxDistance}`);

    const expectedY =
        defaultPlanetConfig.center.y +
        defaultPlanetConfig.radius * defaultPlanetConfig.scaleY +
        defaultPlanetConfig.flowerYOffset +
        defaultPlanetConfig.flowerFloat;
    assert.ok(approxEqual(placement.position.y, expectedY), '压扁后的高度应保持一致');
});

test('自定义中心高度时，返回坐标会对应新的中心', () => {
    const customConfig = {
        ...defaultPlanetConfig,
        center: { ...defaultPlanetConfig.center, y: -10 }
    };

    const placement = calculateSurfacePlacement({ x: 0, z: 0 }, customConfig);
    const expectedY =
        customConfig.center.y +
        customConfig.radius * customConfig.scaleY +
        customConfig.flowerYOffset +
        customConfig.flowerFloat;

    assert.ok(approxEqual(placement.position.y, expectedY), '应使用新的中心高度计算');
    assert.ok(approxEqual(placement.position.x, 0) && approxEqual(placement.position.z, 0), '中心位置应保持原点');
});

