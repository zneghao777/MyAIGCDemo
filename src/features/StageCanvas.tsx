"use client";
import { uiCopy, formatCopy } from "@/features/creative/copy";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  Grid,
  OrbitControls,
  TransformControls,
  Html,
  Line,
  PerspectiveCamera,
} from "@react-three/drei";
import { Component, useEffect, useRef, type ReactNode } from "react";
import * as THREE from "three";
import type { DirectorData, StageObject, Vector } from "@/lib/types";
function positionAt(
  o: StageObject,
  d: DirectorData,
  time: number,
  playing: boolean,
): Vector {
  if (!playing) return o.position;
  const keys = d.keyframes
    .filter((k) => k.objectId === o.id)
    .sort((a, b) => a.t - b.t);
  if (!keys.length) return o.position;
  if (time <= keys[0].t) return keys[0].position;
  for (let i = 1; i < keys.length; i++) {
    if (time <= keys[i].t) {
      const a = keys[i - 1],
        b = keys[i],
        f = (time - a.t) / (b.t - a.t || 1);
      return a.position.map((n, j) => n + (b.position[j] - n) * f) as Vector;
    }
  }
  return keys.at(-1)!.position;
}
function Shape({ o }: { o: StageObject }) {
  return o.kind === "actor" ? (
    <>
      <mesh position={[0, 1, 0]} castShadow>
        <capsuleGeometry args={[0.22, 0.7, 6, 12]} />
        <meshStandardMaterial color={o.color} roughness={0.6} />
      </mesh>
      <mesh position={[0, 1.72, 0]} castShadow>
        <sphereGeometry args={[0.2, 20, 20]} />
        <meshStandardMaterial color={o.color} />
      </mesh>
      <mesh position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.35, 0.4, 32]} />
        <meshBasicMaterial color={o.color} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, 0.2, -0.65]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.11, 0.25, 3]} />
        <meshBasicMaterial color={o.color} />
      </mesh>
    </>
  ) : o.kind === "camera" ? (
    <>
      <mesh>
        <boxGeometry args={[0.5, 0.3, 0.4]} />
        <meshStandardMaterial color="#303540" />
      </mesh>
      <mesh position={[0, 0, -0.4]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.18, 0.23, 0.3, 16]} />
        <meshStandardMaterial color={o.color} />
      </mesh>
      <Line
        color={o.color}
        points={[
          [0, 0, 0],
          [-0.65, -0.4, -1.4],
          [0.65, -0.4, -1.4],
          [0, 0, 0],
          [-0.65, 0.4, -1.4],
          [0.65, 0.4, -1.4],
          [0, 0, 0],
          [0.65, -0.4, -1.4],
          [0.65, 0.4, -1.4],
          [-0.65, 0.4, -1.4],
          [-0.65, -0.4, -1.4],
        ]}
        lineWidth={1}
      />
    </>
  ) : (
    <>
      <mesh position={[0, 0.7, 0]} castShadow>
        <boxGeometry args={[1.5, 0.12, 0.9]} />
        <meshStandardMaterial color="#65646d" />
      </mesh>
      {[-0.6, 0.6].flatMap((x) =>
        [-0.3, 0.3].map((z) => (
          <mesh key={`${x}${z}`} position={[x, 0.35, z]}>
            <boxGeometry args={[0.07, 0.7, 0.07]} />
            <meshStandardMaterial color="#4f505a" />
          </mesh>
        )),
      )}
    </>
  );
}
function StageItem({
  o,
  data,
  selected,
  onSelect,
  onChange,
  mode,
  time,
  playing,
  preview,
}: {
  o: StageObject;
  data: DirectorData;
  selected: string;
  onSelect: (s: string) => void;
  onChange: (id: string, p: Partial<StageObject>) => void;
  mode: "translate" | "rotate" | "scale";
  time: number;
  playing: boolean;
  preview: boolean;
}) {
  const ref = useRef<THREE.Group>(null);
  const pos = positionAt(o, data, time, playing);
  const group = (
    <group
      ref={ref}
      position={pos}
      rotation={o.rotation}
      scale={o.scale}
      onClick={(e) => {
        if (preview) return;
        e.stopPropagation();
        onSelect(o.id);
      }}
    >
      <Shape o={o} />
      {!preview ? (
        <Html
          position={[0, o.kind === "actor" ? 2.1 : 1.3, 0]}
          center
          distanceFactor={9}
          style={{ pointerEvents: "none" }}
        >
          <div className={`stage-label ${selected === o.id ? "active" : ""}`}>
            {o.name}
          </div>
        </Html>
      ) : null}
    </group>
  );
  return selected === o.id && !playing && !preview ? (
    <TransformControls
      mode={mode}
      translationSnap={0.25}
      rotationSnap={Math.PI / 12}
      onMouseUp={() => {
        const g = ref.current;
        if (g)
          onChange(o.id, {
            position: g.position.toArray() as Vector,
            rotation: [g.rotation.x, g.rotation.y, g.rotation.z],
            scale: g.scale.x,
          });
      }}
    >
      {group}
    </TransformControls>
  ) : (
    group
  );
}
function CameraView({
  data,
  time,
  playing,
}: {
  data: DirectorData;
  time: number;
  playing: boolean;
}) {
  const ref = useRef<THREE.PerspectiveCamera>(null);
  const o = data.objects.find((o) => o.kind === "camera");
  const actor = data.objects.find((o) => o.kind === "actor");
  useFrame(() => {
    if (ref.current && o) {
      ref.current.position.set(...positionAt(o, data, time, playing));
      const pos = actor ? positionAt(actor, data, time, playing) : [0, 0, 0];
      ref.current.lookAt(pos[0], 1, pos[2]);
      ref.current.fov = data.fov;
      ref.current.updateProjectionMatrix();
    }
  });
  return (
    <PerspectiveCamera
      ref={ref}
      makeDefault
      position={o?.position || [0, 2, 5]}
      fov={data.fov}
    />
  );
}
function World({
  data,
  selected,
  onSelect,
  onChange,
  mode,
  time,
  playing,
  preview = false,
}: {
  data: DirectorData;
  selected: string;
  onSelect: (s: string) => void;
  onChange: (id: string, p: Partial<StageObject>) => void;
  mode: "translate" | "rotate" | "scale";
  time: number;
  playing: boolean;
  preview?: boolean;
}) {
  return (
    <>
      <color attach="background" args={["#11141a"]} />
      <ambientLight intensity={1.2} />
      <directionalLight position={[5, 8, 3]} intensity={2} castShadow />
      <directionalLight position={[-4, 3, -3]} intensity={1} color="#9eafff" />
      <Grid
        args={[24, 24]}
        cellSize={1}
        cellThickness={0.6}
        cellColor="#30363f"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#4b4537"
        fadeDistance={25}
        position={[0, -0.02, 0]}
      />
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.04, 0]}
        receiveShadow
      >
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="#171a21" />
      </mesh>
      {data.template !== uiCopy["空房间"] ? (
        [-1, 1].map((side) => (
          <group key={side}>
            {[0, 1, 2, 3].map((i) => (
              <mesh
                key={i}
                position={[side * (3.8 + (i % 2)), 1 + (i % 3), -i * 3 + 2]}
              >
                <boxGeometry args={[1.6, (1 + (i % 3)) * 2, 2]} />
                <meshStandardMaterial
                  color={data.template === uiCopy["森林"] ? "#30463c" : "#323640"}
                  transparent
                  opacity={0.7}
                />
              </mesh>
            ))}
          </group>
        ))
      ) : (
        <>
          <mesh position={[0, 1.5, -4]}>
            <boxGeometry args={[10, 3, 0.15]} />
            <meshStandardMaterial color="#343740" />
          </mesh>
          <mesh position={[-5, 1.5, 0]}>
            <boxGeometry args={[0.15, 3, 8]} />
            <meshStandardMaterial color="#343740" />
          </mesh>
        </>
      )}
      {data.objects
        .filter((o) => !preview || o.kind !== "camera")
        .map((o) => (
          <StageItem
            key={o.id}
            {...{
              o,
              data,
              selected,
              onSelect,
              onChange,
              mode,
              time,
              playing,
              preview,
            }}
          />
        ))}
      {!preview
        ? data.objects.map((o) => {
            const points = data.keyframes
              .filter((k) => k.objectId === o.id)
              .sort((a, b) => a.t - b.t)
              .map((k) => [k.position[0], 0.07, k.position[2]] as Vector);
            return points.length > 1 ? (
              <Line
                key={o.id}
                points={points}
                color={o.color}
                dashed
                dashSize={0.15}
                gapSize={0.1}
                lineWidth={1.5}
              />
            ) : null;
          })
        : null}
      {preview ? (
        <CameraView data={data} time={time} playing={playing} />
      ) : (
        <OrbitControls
          makeDefault
          target={[0, 0.6, -0.7]}
          minDistance={3}
          maxDistance={30}
          maxPolarAngle={Math.PI / 2 - 0.05}
        />
      )}
    </>
  );
}
class StageErrorBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="empty">
        <h3>{uiCopy["3D 视口暂时无法启动"]}</h3>
        <p>{uiCopy["请启用浏览器硬件加速后刷新。右侧数值编辑仍然可用。"]}</p>
      </div>
    ) : (
      this.props.children
    );
  }
}
export default function StageCanvas(props: Parameters<typeof World>[0]) {
  return (
    <StageErrorBoundary>
      <Canvas
        shadows
        camera={{ position: [8, 7, 10], fov: 45 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true }}
      >
        <World {...props} />
      </Canvas>
    </StageErrorBoundary>
  );
}
