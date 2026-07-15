# yuleOSH Desktop Assets

Place your icon files here:

| File | Purpose | Format | Size |
|---|---|---|---|
| `icon.png` | App icon (Linux) | PNG | 512×512 |
| `icon.icns` | App icon (macOS) | ICNS | 512×512 |
| `iconTemplate.png` | Tray icon (macOS, Template format) | PNG | 22×22, monochrome |
| `tray-error.png` | Error state tray icon | PNG | 22×22 |
| `dmg-background.png` | DMG background (optional) | PNG | 660×400 |
| `entitlements.mac.plist` | macOS code signing entitlements | plist | — |

## Icon Template Guide (macOS)

For macOS tray icon:
- Use pure black/white design (no gray shades)
- macOS automatically inverts for dark mode when filename contains "Template"
- Name the file `iconTemplate.png` (not `iconTemplate@2x.png`)
- Recommended size: 22×22pt (44×44px @2x for Retina)

## Generating Icons

You can use any icon tool (Sketch, Figma, Photoshop) or convert from SVG:

```bash
# Convert SVG to PNG (using librsvg or ImageMagick)
rsvg-convert -w 512 -h 512 icon.svg > icon.png
rsvg-convert -w 22 -h 22 icon.svg > iconTemplate.png
```

## Entitlements

For macOS code signing, create `entitlements.mac.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
</dict>
</plist>
```
