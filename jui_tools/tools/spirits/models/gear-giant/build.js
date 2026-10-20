// Gear Giant (bundled, an original): a brass giant of gears and two heavy arms that punch in turn, fast, behind
// the robot. The robot wears goggles in place of its headband.
import * as THREE from 'three';

export const clips = { appear: 0.6, loop: 1.2, leave: 0.5 };

const BRASS = 0xc8a040;
const DARK = 0x5a4020;
const STEEL = 0x8a949e;

function mat(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.7, ...extra });
}

function mesh(name, geo, m, x = 0, y = 0, z = 0) {
  const o = new THREE.Mesh(geo, m);
  o.name = name;
  o.position.set(x, y, z);
  return o;
}

// a flat gear with teeth: one extruded shape with a hole, facing +z
function gearGeometry(radius, teeth, depth) {
  const shape = new THREE.Shape();
  const inner = radius * 0.86;
  for (let i = 0; i < teeth * 4; i++) {
    const a = (i / (teeth * 4)) * Math.PI * 2;
    const r = i % 4 === 1 || i % 4 === 2 ? radius : inner;
    if (i === 0) shape.moveTo(Math.cos(a) * r, Math.sin(a) * r);
    else shape.lineTo(Math.cos(a) * r, Math.sin(a) * r);
  }
  shape.closePath();
  const hole = new THREE.Path();
  hole.absarc(0, 0, radius * 0.3, 0, Math.PI * 2, true);
  shape.holes.push(hole);
  const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 4 });
  geo.translate(0, 0, -depth / 2);
  return geo;
}

function gear(name, radius, teeth, color, x, y, z) {
  const g = mesh(name, gearGeometry(radius, teeth, 0.12), mat(color), x, y, z);
  g.add(mesh(`${name}Hub`, new THREE.CylinderGeometry(radius * 0.32, radius * 0.32, 0.16, 12), mat(DARK), 0, 0, 0));
  g.children[0].rotation.x = Math.PI / 2;
  return g;
}

function arm(side) {
  const shoulder = new THREE.Group();
  shoulder.name = `${side}Shoulder`;
  shoulder.add(mesh(`${side}Joint`, new THREE.SphereGeometry(0.26, 14, 10), mat(DARK)));
  const upper = mesh(`${side}Upper`, new THREE.CylinderGeometry(0.16, 0.2, 0.7, 12), mat(BRASS), 0, 0, 0.4);
  upper.rotation.x = Math.PI / 2;
  const elbow = new THREE.Group();
  elbow.name = `${side}Elbow`;
  elbow.position.set(0, 0, 0.78);
  elbow.add(mesh(`${side}Fore`, new THREE.BoxGeometry(0.3, 0.3, 0.6), mat(BRASS), 0, 0, 0.3));
  elbow.add(mesh(`${side}Fist`, new THREE.BoxGeometry(0.42, 0.4, 0.36), mat(STEEL), 0, 0, 0.72));
  shoulder.add(upper, elbow);
  return { shoulder, elbow };
}

export function build() {
  const spirit = new THREE.Group();
  spirit.name = 'gearGiant';
  const body = new THREE.Group();
  body.name = 'body';
  spirit.add(body);

  const chest = gear('chestGear', 0.75, 18, BRASS, 0, 2.2, 0);
  const side1 = gear('sideGear', 0.42, 12, DARK, -0.62, 1.55, 0.08);
  const side2 = gear('backGear', 0.5, 14, BRASS, 0.58, 1.5, -0.1);
  const waist = mesh('waist', new THREE.CylinderGeometry(0.3, 0.55, 0.9, 16), mat(DARK), 0, 1.2, -0.05);
  body.add(chest, side1, side2, waist);

  const head = new THREE.Group();
  head.name = 'head';
  head.position.set(0, 3.15, 0.05);
  const crown = gear('crownGear', 0.36, 10, BRASS, 0, 0, 0);
  head.add(crown);
  head.add(mesh('eye', new THREE.SphereGeometry(0.12, 14, 10), mat(0xffd060, { emissive: 0xffa020, emissiveIntensity: 1.2, metalness: 0 }), 0, 0, 0.12));
  body.add(head);

  const right = arm('right');
  right.shoulder.position.set(0.95, 2.4, 0.1);
  const left = arm('left');
  left.shoulder.position.set(-0.95, 2.4, 0.1);
  body.add(right.shoulder, left.shoulder);

  // the robot's goggles, in the head's own coordinates, where its headband was (y 0.645; spirit.json hides "band")
  const goggles = new THREE.Group();
  goggles.name = 'goggles';
  const strap = mat(0x3a2a1a, { metalness: 0, roughness: 0.9 });
  goggles.add(mesh('strapFront', new THREE.BoxGeometry(1.14, 0.16, 0.03), strap, 0, 0.645, 0.475));
  goggles.add(mesh('strapBack', new THREE.BoxGeometry(1.14, 0.16, 0.03), strap, 0, 0.645, -0.475));
  for (const s of [-1, 1]) goggles.add(mesh(`strap${s < 0 ? 'L' : 'R'}`, new THREE.BoxGeometry(0.03, 0.16, 0.98), strap, s * 0.575, 0.645, 0));
  for (const s of [-1, 1]) {
    const cup = mesh(`cup${s < 0 ? 'L' : 'R'}`, new THREE.CylinderGeometry(0.17, 0.19, 0.12, 18), mat(BRASS), s * 0.24, 0.645, 0.53);
    cup.rotation.x = Math.PI / 2;
    cup.add(mesh(`glass${s < 0 ? 'L' : 'R'}`, new THREE.CylinderGeometry(0.13, 0.13, 0.02, 18), mat(0x88d8ff, { metalness: 0.1, roughness: 0.1, emissive: 0x204060 }), 0, 0.065, 0));
    goggles.add(cup);
  }

  function animate(t, clip) {
    const k = clip === 'appear' ? t / clips.appear : clip === 'leave' ? 1 - t / clips.leave : 1;
    const ease = k * k * (3 - 2 * k);
    body.position.y = -0.8 * (1 - ease);
    spirit.scale.setScalar(0.5 + 0.5 * ease);
    const turn = (t / (clip === 'loop' ? clips.loop : 1)) * Math.PI * 2;
    chest.rotation.z = clip === 'loop' ? -turn : 0;
    side1.rotation.z = clip === 'loop' ? turn * (18 / 12) : 0;
    side2.rotation.z = clip === 'loop' ? turn * (18 / 14) : 0;
    crown.rotation.z = clip === 'loop' ? turn * 2 : 0;
    // the rush: four punches a second, the arms in turn; each jab out fast and back
    const beat = clip === 'loop' ? (t / clips.loop) * 4 : 0;
    const jab = (p) => Math.pow(Math.max(0, Math.sin(p * Math.PI * 2)), 0.5);
    const r = jab(beat), l = jab(beat + 0.5);
    right.shoulder.rotation.set(0.15 - r * 0.25, -0.35 + r * 0.25, 0);
    right.elbow.rotation.x = 1.1 * (1 - r);
    left.shoulder.rotation.set(0.15 - l * 0.25, 0.35 - l * 0.25, 0);
    left.elbow.rotation.x = 1.1 * (1 - l);
    body.rotation.y = (r - l) * 0.12;
  }
  animate(0, 'loop');
  return { spirit, parts: [{ name: 'goggles', object: goggles }], clips, animate };
}
