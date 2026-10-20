// Ink Scholar (bundled, an original): a scholar in ink, shoulders up, who writes with a long brush behind the
// robot. The robot wears round glasses and holds a half-open scroll in its left hand.
import * as THREE from 'three';

export const clips = { appear: 0.8, loop: 2.4, leave: 0.6 };

const INK = 0x1c2430;
const SLEEVE = 0x2c3a48;
const PAPER = 0xe8e0c8;

function mat(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra });
}

function mesh(name, geo, m, x = 0, y = 0, z = 0) {
  const o = new THREE.Mesh(geo, m);
  o.name = name;
  o.position.set(x, y, z);
  return o;
}

function sleeveArm(side) {
  // shoulder pivot, a flaring sleeve, a forearm and a hand
  const arm = new THREE.Group();
  arm.name = `${side}Arm`;
  const sleeve = mesh(`${side}Sleeve`, new THREE.CylinderGeometry(0.16, 0.34, 0.9, 14, 1, true), mat(SLEEVE, { side: THREE.DoubleSide }), 0, -0.45, 0);
  const fore = new THREE.Group();
  fore.name = `${side}Fore`;
  fore.position.set(0, -0.85, 0);
  fore.add(mesh(`${side}Wrist`, new THREE.CylinderGeometry(0.07, 0.08, 0.42, 10), mat(INK), 0, -0.2, 0));
  fore.add(mesh(`${side}Hand`, new THREE.SphereGeometry(0.1, 12, 10), mat(INK), 0, -0.44, 0));
  arm.add(sleeve, fore);
  return { arm, fore };
}

export function build() {
  const spirit = new THREE.Group();
  spirit.name = 'inkScholar';
  const body = new THREE.Group();
  body.name = 'body';
  spirit.add(body);

  // a robe that narrows into ink at the bottom: a lathe from the waist up
  const robe = [[0.05, 0], [0.42, 0.1], [0.62, 0.7], [0.66, 1.3], [0.5, 1.75], [0.2, 1.95], [0.12, 2.0]].map(([x, y]) => new THREE.Vector2(x, y));
  body.add(mesh('robe', new THREE.LatheGeometry(robe, 24), mat(INK), 0, 0.6, 0));
  // a collar crossing at the front
  const collar = mesh('collar', new THREE.TorusGeometry(0.3, 0.05, 8, 24, Math.PI * 1.2), mat(PAPER), 0, 2.45, 0.12);
  collar.rotation.set(Math.PI / 2.2, 0, Math.PI * 0.9);
  body.add(collar);

  const head = new THREE.Group();
  head.name = 'head';
  head.position.set(0, 2.85, 0);
  head.add(mesh('face', new THREE.SphereGeometry(0.34, 20, 16), mat(INK)));
  head.add(mesh('bun', new THREE.SphereGeometry(0.15, 14, 10), mat(INK), 0, 0.34, -0.08));
  const pin = mesh('pin', new THREE.CylinderGeometry(0.015, 0.015, 0.5, 6), mat(PAPER), 0, 0.36, -0.08);
  pin.rotation.z = Math.PI / 2;
  head.add(pin);
  // two calm eyes, drawn as thin pale slits
  for (const x of [-0.12, 0.12]) head.add(mesh(`eye${x < 0 ? 'L' : 'R'}`, new THREE.BoxGeometry(0.11, 0.018, 0.02), mat(PAPER, { emissive: PAPER, emissiveIntensity: 0.6 }), x, 0.02, 0.32));
  body.add(head);

  const right = sleeveArm('right');
  right.arm.position.set(0.55, 2.35, 0.05);
  const left = sleeveArm('left');
  left.arm.position.set(-0.55, 2.35, 0.05);
  body.add(right.arm, left.arm);
  // the brush in the right hand: a bamboo handle and a soft ink tip
  const brush = new THREE.Group();
  brush.name = 'brush';
  brush.position.set(0, -0.48, 0.05);
  brush.add(mesh('brushHandle', new THREE.CylinderGeometry(0.025, 0.03, 0.7, 8), mat(0x8a7040), 0, 0.05, 0));
  brush.add(mesh('brushTip', new THREE.ConeGeometry(0.05, 0.18, 10), mat(INK), 0, -0.38, 0));
  brush.children[1].rotation.x = Math.PI;
  right.fore.add(brush);

  // the robot's round glasses, in the head's own coordinates (spirit.json parts at "head")
  const glasses = new THREE.Group();
  glasses.name = 'glasses';
  const rim = mat(0x302820, { metalness: 0.4, roughness: 0.4 });
  for (const x of [-0.21, 0.21]) glasses.add(mesh(`lens${x < 0 ? 'L' : 'R'}`, new THREE.TorusGeometry(0.13, 0.018, 8, 28), rim, x, 0.42, 0.49));
  glasses.add(mesh('bridge', new THREE.BoxGeometry(0.16, 0.02, 0.02), rim, 0, 0.45, 0.49));
  // from each lens's outer edge to the side of the head (half its width: 0.55), then back along it
  for (const s of [-1, 1]) {
    glasses.add(mesh(`hinge${s < 0 ? 'L' : 'R'}`, new THREE.BoxGeometry(0.22, 0.02, 0.02), rim, s * 0.445, 0.44, 0.49));
    glasses.add(mesh(`temple${s < 0 ? 'L' : 'R'}`, new THREE.BoxGeometry(0.02, 0.02, 0.5), rim, s * 0.56, 0.44, 0.24));
  }

  // the scroll in the robot's left hand (spirit.json props at "handL"): a rod and a sheet half unrolled
  const scroll = new THREE.Group();
  scroll.name = 'scroll';
  const rod = mesh('scrollRod', new THREE.CylinderGeometry(0.05, 0.05, 0.46, 12), mat(0x6a4a2a), 0, 0, 0);
  rod.rotation.z = Math.PI / 2;
  const sheet = mesh('scrollSheet', new THREE.PlaneGeometry(0.42, 0.34), mat(PAPER, { side: THREE.DoubleSide }), 0, 0.17, 0.04);
  sheet.rotation.x = -0.35;
  for (let i = 0; i < 4; i++) sheet.add(mesh(`line${i}`, new THREE.BoxGeometry(0.012, 0.22, 0.004), mat(INK), -0.12 + i * 0.08, 0, 0.004));
  scroll.add(rod, sheet);

  function animate(t, clip) {
    const k = clip === 'appear' ? t / clips.appear : clip === 'leave' ? 1 - t / clips.leave : 1;
    const ease = k * k * (3 - 2 * k);
    // appear: rises out of the ink and grows; leave: sinks back
    body.position.y = -1.2 * (1 - ease);
    spirit.scale.setScalar(0.6 + 0.4 * ease);
    const w = clip === 'loop' ? (t / clips.loop) * Math.PI * 2 : 0;
    // writing: the right arm sweeps a column of strokes, the head follows, the left sleeve sways
    right.arm.rotation.set(-0.9 + Math.sin(w * 2) * 0.18, 0, 0.35 + Math.sin(w) * 0.2);
    right.fore.rotation.x = -0.6 + Math.cos(w * 2) * 0.25;
    left.arm.rotation.set(-0.2 + Math.sin(w + 1) * 0.05, 0, -0.25);
    left.fore.rotation.x = -0.3;
    head.rotation.set(0.25 + Math.sin(w * 2) * 0.06, Math.sin(w) * 0.12, 0);
    body.rotation.y = Math.sin(w) * 0.05;
    sheet.rotation.x = -0.35 + Math.sin(w) * 0.04;
  }
  animate(0, 'loop');
  return {
    spirit,
    parts: [{ name: 'glasses', object: glasses }],
    props: [{ name: 'scroll', object: scroll }],
    clips,
    animate,
  };
}
