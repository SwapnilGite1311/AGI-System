# Installation Guide

This guide provides detailed installation instructions for ASC (Autonomous System Controller) across different platforms and deployment scenarios.

## Table of Contents

- [System Requirements](#system-requirements)
- [Local Installation](#local-installation)
- [Docker Installation](#docker-installation)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## System Requirements

### Minimum Requirements

- **Operating System**: Windows 10+, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **Python**: 3.13 or higher
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 10GB free space
- **Network**: Internet connection for Ollama model downloads (optional)

### Recommended Requirements

- **Operating System**: Windows 11, macOS 12+, or Ubuntu 22.04+
- **Python**: 3.13+
- **RAM**: 16GB minimum, 32GB recommended for full LLM functionality
- **Storage**: 20GB free space for models and data
- **GPU**: NVIDIA GPU with 8GB+ VRAM (optional, for accelerated inference)
- **Network**: Stable internet connection for model downloads and API access

## Local Installation

### Windows Installation

#### Step 1: Install Python

1. Download Python 3.13+ from [python.org](https://www.python.org/downloads/)
2. Run the installer and check "Add Python to PATH"
3. Verify installation:
   ```bash
   python --version
   pip --version
   ```

#### Step 2: Install Git

1. Download Git from [git-scm.com](https://git-scm.com/download/win)
2. Run the installer with default settings
3. Verify installation:
   ```bash
   git --version
   ```

#### Step 3: Clone Repository

```bash
git clone https://github.com/yourusername/AGI-System.git
cd AGI-System
```

#### Step 4: Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

#### Step 5: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 6: Install Ollama (Optional but Recommended)

1. Download Ollama from [ollama.ai](https://ollama.ai/download)
2. Run the installer
3. Verify installation:
   ```bash
   ollama --version
   ```

#### Step 7: Install Ollama Models

```bash
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull llava:7b
ollama pull gemma2:2b
ollama pull tinyllama
```

#### Step 8: Install Playwright

```bash
playwright install chromium
```

#### Step 9: Configure System

```bash
# Copy configuration template
copy config\settings.json config\settings.json.backup

# Edit configuration with your settings
notepad config\settings.json
```

#### Step 10: Run Tests

```bash
python -m pytest tests -v
```

#### Step 11: Start ASC

```bash
python main.py
```

### macOS Installation

#### Step 1: Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Step 2: Install Python

```bash
brew install python@3.13
```

#### Step 3: Clone Repository

```bash
git clone https://github.com/yourusername/AGI-System.git
cd AGI-System
```

#### Step 4: Create Virtual Environment

```bash
python3.13 -m venv venv
source venv/bin/activate
```

#### Step 5: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 6: Install Ollama

```bash
brew install ollama
```

#### Step 7: Install Ollama Models

```bash
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull llava:7b
ollama pull gemma2:2b
ollama pull tinyllama
```

#### Step 8: Install Playwright

```bash
playwright install chromium
```

#### Step 9: Configure System

```bash
cp config/settings.json config/settings.json.backup
nano config/settings.json
```

#### Step 10: Run Tests

```bash
python -m pytest tests -v
```

#### Step 11: Start ASC

```bash
python main.py
```

### Linux Installation

#### Step 1: Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3.13 python3-pip git curl
```

#### Step 2: Clone Repository

```bash
git clone https://github.com/yourusername/AGI-System.git
cd AGI-System
```

#### Step 3: Create Virtual Environment

```bash
python3.13 -m venv venv
source venv/bin/activate
```

#### Step 4: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 5: Install Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

#### Step 6: Install Ollama Models

```bash
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull llava:7b
ollama pull gemma2:2b
ollama pull tinyllama
```

#### Step 7: Install Playwright Dependencies

```bash
playwright install-deps chromium
playwright install chromium
```

#### Step 8: Configure System

```bash
cp config/settings.json config/settings.json.backup
nano config/settings.json
```

#### Step 9: Run Tests

```bash
python -m pytest tests -v
```

#### Step 10: Start ASC

```bash
python main.py
```

## Docker Installation

### Build Docker Image

```bash
# Build the image
docker build -t asc:latest .

# Or build with specific Python version
docker build --build-arg PYTHON_VERSION=3.13 -t asc:latest .
```

### Run Docker Container

```bash
# Run with default configuration
docker run -d -p 5000:5000 --name asc asc:latest

# Run with custom configuration
docker run -d -p 5000:5000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  --name asc asc:latest

# Run with GPU support (NVIDIA)
docker run -d -p 5000:5000 \
  --gpus all \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  --name asc asc:latest
```

### Docker Compose

```bash
# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Production Deployment

### Systemd Service (Linux)

#### Create Service File

```bash
sudo nano /etc/systemd/system/asc.service
```

#### Service Configuration

```ini
[Unit]
Description=Autonomous System Controller
After=network.target

[Service]
Type=simple
User=asc
Group=asc
WorkingDirectory=/opt/asc
Environment="PATH=/opt/asc/venv/bin"
ExecStart=/opt/asc/venv/bin/python /opt/asc/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable asc.service
sudo systemctl start asc.service
sudo systemctl status asc.service
```

### Windows Service

#### Using NSSM

1. Download NSSM from [nssm.cc](https://nssm.cc/download)
2. Install ASC as a service:
   ```bash
   nssm install ASC "C:\Python313\python.exe" "C:\AGI-System\main.py"
   nssm set ASC AppDirectory "C:\AGI-System"
   nssm set ASC DisplayName "Autonomous System Controller"
   nssm set ASC Description "Intelligent local AI assistant"
   nssm start ASC
   ```

#### Using Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: "At startup"
4. Action: "Start a program"
5. Program: `python.exe`
6. Arguments: `main.py`
7. Start in: `C:\AGI-System`
8. Finish and enable task

### macOS Launch Agent

#### Create Launch Agent

```bash
~/Library/LaunchAgents/com.asc.plist
```

#### Launch Agent Configuration

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.asc</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/asc/venv/bin/python</string>
        <string>/opt/asc/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/asc</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

#### Load Launch Agent

```bash
launchctl load ~/Library/LaunchAgents/com.asc.plist
launchctl start com.asc
```

## Configuration

### Environment Variables

```bash
# ASC Configuration
export ASC_CONFIG_PATH="/path/to/config/settings.json"
export ASC_DATA_DIR="/path/to/data"
export ASC_LOG_LEVEL="INFO"
export ASC_PORT=5000

# Ollama Configuration
export OLLAMA_HOST="http://127.0.0.1:11434"
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=0

# Email Configuration
export ASC_SMTP_SERVER="smtp.gmail.com"
export ASC_SMTP_PORT=587
export ASC_EMAIL_ADDRESS="your@gmail.com"
export ASC_EMAIL_PASSWORD="your_app_password"

# External API Keys
export ASC_WEATHER_API_KEY="your_weather_api_key"
export ASC_NEWS_API_KEY="your_news_api_key"
export ASC_STOCK_API_KEY="your_stock_api_key"
```

### Configuration File

Edit `config/settings.json`:

```json
{
  "ollama": {
    "host": "http://127.0.0.1:11434",
    "models": {
      "chairman": "qwen2.5:14b",
      "strategist": "qwen2.5:7b",
      "executor": "llama3.1:8b",
      "analyst": "mistral:7b",
      "vision": "llava:7b",
      "speed": "gemma2:2b"
    }
  },
  "execution": {
    "command_cache_size": 100,
    "direct_pause_seconds": 0.3,
    "decompose_complex_tasks": true
  },
  "audio": {
    "voice_enabled": false,
    "voice_service_url": "http://localhost:5000"
  }
}
```

## Troubleshooting

### Common Issues

#### Python Version Incompatibility

**Problem**: `SyntaxError` or import errors
**Solution**: Ensure Python 3.13+ is installed and activated in virtual environment

```bash
python --version  # Should be 3.13+
```

#### Ollama Connection Failed

**Problem**: `Connection refused` when connecting to Ollama
**Solution**: Start Ollama service

```bash
# Windows
ollama serve

# macOS/Linux
ollama serve &
```

#### Playwright Browser Issues

**Problem**: Browser automation fails
**Solution**: Install Playwright browsers

```bash
playwright install chromium
playwright install-deps chromium
```

#### Memory Issues

**Problem**: System runs out of RAM
**Solution**: Reduce model size or use smaller models

```json
{
  "ollama": {
    "models": {
      "chairman": "gemma2:2b",
      "strategist": "gemma2:2b",
      "executor": "gemma2:2b"
    }
  }
}
```

#### Permission Errors

**Problem**: File access denied errors
**Solution**: Run with appropriate permissions

```bash
# Linux/macOS
chmod +x main.py

# Windows: Run as Administrator
```

### Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/yourusername/AGI-System/issues)
2. Review the [Documentation](docs/)
3. Ask in [GitHub Discussions](https://github.com/yourusername/AGI-System/discussions)
4. Contact support at support@asc.example.com

---

**Next**: [API Documentation](API_DOCUMENTATION.md)