/**
 * electron-builder afterPack 钩子：为 macOS 产物补 ad-hoc 签名。
 *
 * 背景：项目在无 Apple 开发者证书时以 identity: null 跳过签名。未签名的
 * arm64 应用会被 macOS 判定为「已损坏，无法打开」。这里在 .app 打包完成、
 * 生成 dmg/zip 之前，用 `codesign --sign -` 打上 ad-hoc 签名，使产物至少
 * 满足 arm64 的签名要求（Gatekeeper 仍会提示未验证开发者，需右键打开）。
 *
 * 仅在 darwin 平台执行；其他平台直接跳过。
 */
const { execFileSync } = require("node:child_process");
const path = require("node:path");

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") {
    return;
  }

  const appPath = path.join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`
  );

  console.log(`[after-pack] ad-hoc signing: ${appPath}`);
  execFileSync(
    "codesign",
    [
      "--force",
      "--deep",
      "--sign",
      "-",
      "--timestamp=none",
      appPath,
    ],
    { stdio: "inherit" }
  );

  // 签名结果自检，签名失败时让构建直接红掉，避免产出无法打开的包。
  execFileSync("codesign", ["--verify", "--deep", "--strict", appPath], {
    stdio: "inherit",
  });
  console.log("[after-pack] ad-hoc signature verified");
};
