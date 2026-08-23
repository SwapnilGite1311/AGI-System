# ASC Quick Start Guide

## Prerequisites

1. **Python 3.13+** installed
2. **Ollama** installed and running (optional but recommended for full functionality)
3. **Chromium** browser (for web automation)
4. **Outlook** (for calendar integration, optional)

## Installation

```bash
# Navigate to the project directory
cd "C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\AGI-System"

# Install dependencies
pip install -r requirements.txt

# Install Ollama models (if using Ollama)
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull llava:7b
ollama pull gemma2:2b
ollama pull tinyllama
```

## Running the System

### Interactive Mode (Recommended for Demo)

```bash
python main.py
```

This starts the interactive console where you can give natural language commands.

### Running Tests

```bash
# Run all tests
python -m pytest tests -v

# Run specific test categories
python -m pytest tests/test_basic.py -v
python -m pytest tests/test_phase6_business.py -v
```

## Quick Demo Commands

### 1. Basic Conversation
```
Hello Jarvis, how are you?
What can you do?
```

### 2. System Information
```
Show system status
List running processes
Check disk usage
```

### 3. Task Management (Phase 6)
```
Create task: Prepare interview slides, priority: high, due_date: 2026-09-14
List tasks
Daily plan
```

### 4. Project Management (Phase 6)
```
Create project: Website Redesign, end_date: 2026-09-30
Project status: [project_id]
List projects
```

### 5. Web Automation
```
Open chrome and search for autonomous AI
Navigate to https://example.com
```

### 6. File Operations
```
List files in current directory
Create file: test.txt with content: Hello World
Search for files containing "test"
```

### 7. Learning System
```
Show adaptive learning
Show phase5 learning
Show workflow patterns
```

### 8. Multi-Agent Coordination (Phase 6)
```
Coordinate agents for task: Research and document AI trends
Show agent status
Optimize workflow for task: File organization
```

### 9. Advanced Planning (Phase 6)
```
Open chrome, search for AI trends, then create file named ai_notes.txt
Schedule a meeting to discuss project progress
```

### 10. Calendar Integration (Phase 6)
```
Add calendar event: Team Meeting, 2026-09-15T10:00:00, 2026-09-15T11:00:00
Show upcoming events
```

## Configuration

### Main Configuration File
Edit `config/settings.json` to customize:

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

### Enabling Voice
To enable voice integration:

1. Start the voice service (if you have one configured)
2. Set `voice_enabled: true` in settings.json
3. Use commands like "start voice server" and "stop voice server"

## Troubleshooting

### Ollama Not Running
If you see "Ollama server is not running" errors:

```bash
# Start Ollama
ollama serve

# Or check if it's running
curl http://127.0.0.1:11434/api/tags
```

### Browser Automation Issues
If browser automation fails:

1. Ensure Chromium is installed
2. Check that Playwright is properly installed:
   ```bash
   playwright install chromium
   ```

### Memory Issues
If you encounter memory issues:

1. Reduce model sizes in settings.json
2. Use smaller models (gemma2:2b, tinyllama)
3. Close other applications to free RAM

### Permission Issues
If you encounter permission errors:

1. Run PowerShell as Administrator
2. Check dangerous command patterns in settings.json
3. Ensure file paths are accessible

## Data Storage

ASC stores data in the following locations:

- **Tasks/Projects**: `data/business_tasks.json`, `data/projects.json`
- **Schedules**: `data/schedules.json`
- **Communication Log**: `data/communication_log.json`
- **Phase 5 Model**: `data/phase5_model.json`
- **Adaptive State**: `data/adaptive_state.json`
- **Memory**: ChromaDB (vector storage), SQLite (episodic memory)

## Performance Tips

1. **For Quick Responses**: Use gemma2:2b as the primary model
2. **For Quality**: Use qwen2.5:14b for complex decisions
3. **For Memory**: Ensure sufficient RAM for model loading
4. **For Speed**: Disable voice if not needed
5. **For Testing**: Run tests before live demo to ensure functionality

## Interview Demo Preparation

### Pre-Demo Checklist
- [ ] Ollama is running with required models
- [ ] All tests pass (114+ passing)
- [ ] System status command works
- [ ] Task creation works
- [ ] Web automation works
- [ ] Calendar integration works (if using Outlook)
- [ ] Voice server starts/stops (if using voice)

### Demo Sequence
1. Start the system: `python main.py`
2. Greeting: "Hello Jarvis, how are you?"
3. System status: "Show system status"
4. Task management: "Create task: Demo task, priority: high"
5. Daily plan: "Daily plan"
6. Web automation: "Open chrome and search for AI"
7. Learning: "Show adaptive learning"
8. Multi-agent: "Coordinate agents for task: Research AI"
9. Exit: "Exit"

### Common Demo Issues
- **Browser doesn't open**: Check Chromium installation
- **Task creation fails**: Check data directory permissions
- **Calendar integration fails**: Ensure Outlook is installed
- **Learning shows no data**: Use system more to generate learning data

## Support

For issues or questions:
- Check the logs in the console output
- Review test results: `python -m pytest tests -v`
- Consult the main documentation in `PROJECT_HANDOFF_CONTEXT.md`
- Review interview preparation in `INTERVIEW_PREPARATION.md`

## Version Information

- **Phase 6 Implementation**: Complete
- **Phase 5 Polish**: Complete
- **Jarvis-Like Transformation**: Complete
- **Test Coverage**: 114/119 tests passing
- **Last Updated**: August 15, 2026