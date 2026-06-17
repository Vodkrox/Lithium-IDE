# Lithium IDE
Open Source **AI IDE** that runs **fully locally**.

![banner](/src/assets/lithium_banner.png)
![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![Tkinter](https://img.shields.io/badge/Tkinter-GUI-blue)
![Open Source](https://img.shields.io/badge/Open_Source-Yes-success)
![No Telemetry](https://img.shields.io/badge/Telemetry-None-success)
![Status](https://img.shields.io/badge/Status-Beta-orange)
[![Release](https://img.shields.io/github/v/release/Vodkrox/Lithium-IDE?label=Release&logo=github&color=brightgreen)](https://github.com/Vodkrox/Lithium-IDE/releases)

# Purpose
Provide a fully functional, out-of-the-box AI-powered IDE suitable for everyday development, without relying on paid APIs or third-party servers outside the user's control. It is not designed for Vibe-Coding, but for assistance with the code

# Usage
You can download the latest version from the [releases tab](https://github.com/Vodkrox/Lithium-IDE/releases). You can also run it yourself with Python. Dependencies will be installed automatically.

![screenshot](/src/assets/lithium_screenshot.png)

# First Steps

When you first open the IDE, you will be prompted to **install the required libraries**. Once the installation is complete, **Lithium will restart automatically**.

After restarting, you will be prompted to **download the AI model**. When the download is finished, **Lithium will restart once again**.

After that, **you're ready to start coding**.

# AI Capabilities

- **Edit** the current file or folder
- **Edit** other files or folders
- **Search the web** (Alpha)
- **Reason**
- **Explain code**
- **Auto-approve changes**
- **Run commands**
- **Notify the user**

# AI Levels

The **AI level** is determined by your computer's hardware specifications.

For example, the **Ultra-Low** level is **extremely fast** but has **very limited capabilities**, while the **Ultra-High** level is **slower** but **significantly more capable**.

**Available levels:**

- **Ultra-Low**
- **Low**
- **Low-Medium**
- **Medium**
- **Medium-High**
- **High**
- **Ultra-High**

# Supported Programming Languages

The **programming languages** available in the IDE are imported from **Microsoft's database**.

You can change the selected language to **improve code completion** and **AI-generated responses**.

# Conversations

It is **highly recommended** to start a **new conversation** regularly to avoid saturating the **AI's context window**.

# Default Model

The **default model** (downloaded when the IDE is launched for the first time) is **Qwen 2.5 Coder 7B**.

A **dynamic system prompt** configures the model to provide the **best possible output** depending on the current task.

# Themes

Themes are **embedded into the binary**.

If you are using the **Python version**, you can install additional themes by placing them in `src/themes`.

You can download community themes from **[Awesome-Lithium](https://github.com/Vodkrox/awesome-lithium)** or create your own.

If you create a new theme, please submit a **pull request** to the **Awesome-Lithium** repository!

# Requirements 
- Python 3.x
- pip

## Run from source
```bash
git clone https://github.com/Vodkrox/Lithium-IDE.git
cd Lithium-IDE
python base.py
```
# Notes
This project is not intended for “vibe coding” or fully autonomous generation workflows.
