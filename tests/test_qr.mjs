/**
 * 二维码往返测试（Node 直接跑）。
 *
 * 「配置」面板里给手机扫的那个二维码，错一格就是扫不出来，而它在壳里只能"看着像二维码"。
 * 所以这里做**独立实现之间的往返**：用 qrcode 生成矩阵 → 自己栅格化成 RGBA 位图 → 交给 jsqr
 * 解回来 → 断言解出的文本与原文一模一样。生成方与解码方是两套代码，互为验证。
 *
 * 注意：两个包都装在前端依赖里（qrcode 是运行期依赖、jsqr 只在测试里用），
 * 所以跑之前要先 `cd frontend && npm install`。跑法：node tests/test_qr.mjs
 *
 * 这里用 createRequire 指到 frontend/ 去解析：依赖装在 frontend/node_modules，
 * 而本文件在仓库根目录的 tests/ 下，裸包名在这里是找不到的（现有 Node 测试之所以能
 * import vue，是因为它们 import 的文件本身在 frontend/src 里）。
 */
import { createRequire } from "node:module";

const require = createRequire(new URL("../frontend/", import.meta.url));
const QRCode = require("qrcode");
const jsQR = require("jsqr");

const FAILED = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAILED.push(name);
  console.log(`[${ok ? "ok" : "FAIL"}] ${name}: ${JSON.stringify(got)}` +
              (ok ? "" : ` != ${JSON.stringify(want)}`));
}

// 把 qrcode 的模块矩阵画成 jsqr 要的 RGBA 位图（黑模块 0，白底 255，四边留静区）
function render(qr, scale = 4, quiet = 4) {
  const n = qr.modules.size;
  const data = qr.modules.data;
  const size = (n + quiet * 2) * scale;
  const buf = new Uint8ClampedArray(size * size * 4).fill(255);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      if (!data[y * n + x]) continue;
      for (let dy = 0; dy < scale; dy++) {
        for (let dx = 0; dx < scale; dx++) {
          const i = (((y + quiet) * scale + dy) * size + (x + quiet) * scale + dx) * 4;
          buf[i] = buf[i + 1] = buf[i + 2] = 0;
          buf[i + 3] = 255;
        }
      }
    }
  }
  return { buf, size };
}

function roundTrip(text, opts) {
  const qr = QRCode.create(text, opts);
  const { buf, size } = render(qr);
  const got = jsQR(buf, size, size);
  return got ? got.data : null;
}

// 1) 面板里真实会生成的内容：局域网地址
const url = "http://192.168.1.23:17800";
check("局域网地址往返", roundTrip(url), url);

// 2) 换端口 / 长一点的内网地址也要行（172.16-31 网段、多一位端口）
const url2 = "http://172.20.10.7:17800";
check("另一网段地址往返", roundTrip(url2), url2);

// 3) 面板用的是更低纠错等级吗——不管用哪档，都得能解回来
for (const level of ["L", "M", "Q", "H"]) {
  check(`纠错等级 ${level} 往返`, roundTrip(url, { errorCorrectionLevel: level }), url);
}

// 4) 地址取不到时面板会显示占位而不是二维码：确认空串/中文不会悄悄生成一个"能扫出别的东西"的码
const cn = "http://192.168.1.23:17800/?备注=手机访问";
check("带中文的地址往返", roundTrip(cn), cn);

console.log("");
if (FAILED.length) {
  console.log(`失败 ${FAILED.length} 项：${FAILED.join("、")}`);
  process.exit(1);
}
console.log("二维码往返用例全部通过");
