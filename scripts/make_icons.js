/*
 * PWA用アイコンを生成する(依存なし・Nodeのzlibのみ)。
 *   node scripts/make_icons.js
 * 出力: icons/icon-192.png / icon-512.png / icon-maskable-512.png / apple-touch-icon.png
 *
 * デザイン: ダーク背景(#15161c)にアンバー(#ffb627)のレーダー(同心円+スイープ+ブリップ)。
 */
const zlib = require("zlib");
const fs = require("fs");
const path = require("path");

const BG = [0x15, 0x16, 0x1c];
const AMBER = [0xff, 0xb6, 0x27];

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function chunk(type, data) {
  const t = Buffer.from(type, "latin1");
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}

function encodePNG(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function mix(a, b, t) {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

function drawIcon(size, { padding = 0 } = {}) {
  const rgba = Buffer.alloc(size * size * 4);
  const cx = size / 2;
  const cy = size / 2;
  const R = (size / 2) * (1 - padding); // レーダーの外周半径

  const put = (x, y, rgb, alpha) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const i = (y * size + x) * 4;
    const base = [rgba[i], rgba[i + 1], rgba[i + 2]];
    const out = mix(base, rgb, alpha);
    rgba[i] = out[0];
    rgba[i + 1] = out[1];
    rgba[i + 2] = out[2];
    rgba[i + 3] = 255;
  };

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      rgba[i] = BG[0];
      rgba[i + 1] = BG[1];
      rgba[i + 2] = BG[2];
      rgba[i + 3] = 255;
    }
  }

  const aa = 1.2; // アンチエイリアス幅(px)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - cy;
      const dist = Math.hypot(dx, dy);
      if (dist > R + aa) continue;
      let ang = Math.atan2(dy, dx); // -PI..PI, 0 = 右, 時計回りが下

      // 盤面(ごく淡いアンバー)
      if (dist <= R) put(x, y, AMBER, 0.06);

      // 同心円リング
      for (const rr of [0.34, 0.62, 0.9]) {
        const target = R * rr;
        const d = Math.abs(dist - target);
        if (d < 1.6) put(x, y, AMBER, (1 - d / 1.6) * 0.85);
      }
      // 外周リング(太め)
      {
        const d = Math.abs(dist - R);
        if (d < 2.2) put(x, y, AMBER, (1 - d / 2.2) * 0.95);
      }

      // スイープ(центр→右上、-95°..-5° を回転グラデーション)
      let sweep = ang - (-Math.PI / 12); // 先端を -15° に
      while (sweep < -Math.PI) sweep += Math.PI * 2;
      while (sweep > Math.PI) sweep -= Math.PI * 2;
      if (sweep <= 0 && sweep > -Math.PI * 0.5 && dist <= R) {
        const t = 1 + sweep / (Math.PI * 0.5); // 先端で1, 後端で0
        put(x, y, AMBER, Math.pow(t, 2) * 0.5);
      }

      // 十字ガイド線
      if (dist <= R && (Math.abs(dx) < 0.9 || Math.abs(dy) < 0.9)) {
        put(x, y, AMBER, 0.25);
      }

      // ブリップ(r≈0.62, -15°)
      const bx = cx + R * 0.62 * Math.cos(-Math.PI / 12);
      const by = cy + R * 0.62 * Math.sin(-Math.PI / 12);
      const bd = Math.hypot(x + 0.5 - bx, y + 0.5 - by);
      if (bd < R * 0.09) put(x, y, mix(AMBER, [255, 255, 255], 0.3), Math.max(0, 1 - bd / (R * 0.09)));

      // 中心のドット
      if (dist < R * 0.05) put(x, y, AMBER, 1);
    }
  }
  return encodePNG(size, size, rgba);
}

const outDir = path.resolve(__dirname, "..", "icons");
fs.mkdirSync(outDir, { recursive: true });

const files = {
  "icon-192.png": drawIcon(192, { padding: 0.06 }),
  "icon-512.png": drawIcon(512, { padding: 0.06 }),
  "icon-maskable-512.png": drawIcon(512, { padding: 0.2 }), // セーフゾーン確保
  "apple-touch-icon.png": drawIcon(180, { padding: 0.08 }),
};
for (const [name, buf] of Object.entries(files)) {
  fs.writeFileSync(path.join(outDir, name), buf);
  console.log(`${name}: ${buf.length} bytes`);
}
