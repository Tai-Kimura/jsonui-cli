// A model for the export tool's tests: a box body whose arm swings, a cylinder bent by two bones (the shape a
// tail takes), a cap for the robot's head and a stick for its hand.
import * as THREE from 'three';

export const clips = { appear: 0.5, loop: 1, leave: 0.5 };

function bentCylinder() {
  const geo = new THREE.CylinderGeometry(0.08, 0.08, 1, 8, 8);
  const pos = geo.attributes.position;
  const index = [], weight = [];
  for (let i = 0; i < pos.count; i++) {
    const w = pos.getY(i) + 0.5;
    index.push(0, 1, 0, 0);
    weight.push(1 - w, w, 0, 0);
  }
  geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(index, 4));
  geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(weight, 4));
  const root = new THREE.Bone();
  root.name = 'tailRoot';
  root.position.y = -0.5;
  const tip = new THREE.Bone();
  tip.name = 'tailTip';
  tip.position.y = 1;
  root.add(tip);
  const mesh = new THREE.SkinnedMesh(geo, new THREE.MeshStandardMaterial({ color: 0xd08030 }));
  mesh.name = 'tail';
  mesh.add(root);
  mesh.bind(new THREE.Skeleton([root, tip]));
  mesh.position.set(0.6, 0.5, -0.2);
  return { mesh, tip };
}

export function build() {
  const spirit = new THREE.Group();
  spirit.name = 'blocks';
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.8, 0.4), new THREE.MeshStandardMaterial({ color: 0x4080c0 }));
  body.name = 'body';
  body.position.y = 0.4;
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.5, 0.15), new THREE.MeshStandardMaterial({ color: 0xc0c040 }));
  arm.name = 'arm';
  arm.position.set(-0.4, 0.6, 0);
  const tail = bentCylinder();
  spirit.add(body, arm, tail.mesh);

  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.5, 0.2, 12), new THREE.MeshStandardMaterial({ color: 0xc03030 }));
  cap.name = 'cap';
  cap.position.y = 0.95;
  const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.5, 6), new THREE.MeshStandardMaterial({ color: 0x806040 }));
  stick.name = 'stick';

  function animate(t, clip) {
    const k = clip === 'appear' ? t / clips.appear : clip === 'leave' ? 1 - t / clips.leave : 1;
    spirit.scale.setScalar(0.2 + 0.8 * k);
    arm.rotation.x = clip === 'loop' ? Math.sin((t / clips.loop) * Math.PI * 2) * 0.8 : 0;
    tail.tip.rotation.z = clip === 'loop' ? Math.sin((t / clips.loop) * Math.PI * 2) * 0.6 : 0;
  }
  animate(0, 'loop');
  return { spirit, parts: [{ name: 'cap', object: cap }], props: [{ name: 'stick', object: stick }], clips, animate };
}
