# Krita ComfyUI

A lightweight Krita plug‑in that lets you run **ComfyUI** workflows directly from the Krita UI.  
It focuses on reliable communication between Krita and a running ComfyUI server while leaving workflow design and installation to the user.

> ⚠️ **Compatibility** – Requires Krita 5.2.0+.  
> ⚙️ **GPU** – For local generation you’ll need a GPU with at least 6 GB VRAM (NVIDIA, AMD or Apple Silicon).

---

## Features

| Feature | Description |
|---------|-------------|
| **Generate** | Run any ComfyUI workflow to produce images. |
| **Prompt** | Text‑to‑image from a simple prompt dialog. |
| **Inpainting** | Use Krita selections for generative fill, expansion or object removal. |
| **History** | Browse and preview all previous generations and prompts. |
| **Configure** | Simple UI to connect to your ComfyUI server and select workflows. |
| **UI Style** | Built‑in style presets for a streamlined interface. |

---

## Getting Started

### 1️⃣ Install Krita
Download and install Krita from the [official site](https://krita.org/).  
*Minimum required version:* **5.2.0**

### 2️⃣ Download & Install the Plug‑in
| Step | Action |
|------|--------|
| 1 | Grab the latest release ZIP: <https://github.com/dacert/krita-comfyui/releases/latest> |
| 2 | In Krita, go to `Tools ▸ Scripts ▸ Import Python Plugin from File…` and select the ZIP. |
| 3 | Restart Krita. |

### 3️⃣ Show the Docker
Navigate to `Settings ▸ Dockers ▸ Krita ComfyUi`.

### 4️⃣ Configure the Server
Open the settings window (gear icon) in the docker:

1. **General** tab → Paste your ComfyUI server URL (e.g., `http://localhost:8188/`).  
2. **Workflow** tab → Choose a workflow and set its inputs.

> 👉 If you run a local ComfyUI instance, start it *before* launching Krita so the plug‑in can auto‑connect.

---

## Supported Platforms & Hardware

| OS | GPU support |
|----|-------------|
| Windows, Linux, macOS | • NVIDIA – CUDA (Win/Linux) <br>• AMD – DirectML (Win; limited), ROCm (Linux) <br>• Apple Silicon – MPS (macOS 14+) <br>• CPU – Very slow <br>• XPU – Supported but may be slower |

**Tip:** A powerful GPU (≥6 GB VRAM) will drastically improve generation speed.

---

## Known Issues

- Workflows containing sub‑graphs are not yet supported.  
- If you want to use a pre‑configured workflow, start ComfyUI *before* opening Krita; otherwise the plug‑in won’t load it correctly.

---

## Contributing

We welcome contributions! Please read our [contributing guide](CONTRIBUTING.md) before submitting a pull request.

For bugs or questions, open an issue on GitHub: <https://github.com/dacert/krita-comfyui/issues>.  
Krita’s official channels are not the right place for help with this extension.

---

> **Note** – The plug‑in does *not* install ComfyUI; you must have a running server already.  

Happy painting! 🎨