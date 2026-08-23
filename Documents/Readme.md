# ASC - Autonomous System Controller

**A market-deployable, intelligent local AI assistant that combines natural conversation with practical task automation through a sophisticated multi-agent architecture.**

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-210%20passing-brightgreen.svg)](tests/)
[![Status](https://img.shields.io/badge/status-production--ready-success.svg)](https://github.com)

## 🚀 Overview

ASC (Autonomous System Controller) is a sophisticated local AI assistant designed to behave like Jarvis from Iron Man. It transcends conventional chatbots by combining natural language conversation with practical task automation through a multi-agent architecture.

### Key Features

- **🧠 Intelligent Conversation**: Natural language interaction with Jarvis-like personality
- **🤖 Multi-Agent System**: 17 specialized agents (Conversation, Learning, System, Vision, File, Web, Business, Business Process, Security, Analytics, Advanced Neural, Meta-Learning, Self-Reflection, Autonomous Goals, Concept Discovery, Self-Programming, Algorithm Optimization, Self-Evolving, Cognitive)
- **📊 Business Automation**: Task management, project tracking, scheduling, and analytics
- **🗓️ Calendar Integration**: Multi-platform support (Windows, Google, Apple calendars)
- **📈 Analytics Dashboard**: Business intelligence with productivity metrics and insights
- **🔒 Security-First**: Comprehensive safety protections and credential management
- **🌐 External Integrations**: Weather, news, stock APIs with pre-built connectors
- **👥 Team Collaboration**: Shared workspaces, notifications, and team management
- **🧠 Adaptive Learning**: Neural network-based learning from user patterns
- **🎯 Autonomous Planning**: Advanced task decomposition and execution strategies
- **🏢 Enterprise Features**: ERP/CRM integrations, GDPR compliance, multi-tenant support
- **🤖 Advanced AI/ML**: Ensemble models, predictive analytics, deep learning, anomaly detection

## 📋 Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Features](#features)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## 🏗️ Architecture

### Multi-Agent System

ASC uses a sophisticated multi-agent architecture where each agent specializes in specific domains:

1. **ConversationAgent**: Natural language chat and Q&A with Jarvis personality
2. **LearningAgent**: Adaptive learning from user patterns and feedback
3. **SystemAgent**: OS-level operations and application control
4. **VisionAgent**: OCR and image analysis capabilities
5. **FileAgent**: File management, organization, and search
6. **WebAgent**: Browser automation and form filling
7. **BusinessAgent**: Business workflow automation and project management
8. **BusinessProcessAutomation**: ERP/CRM integrations and process mining
9. **EnterpriseSecurity**: GDPR compliance, audit trails, multi-tenant support
10. **AdvancedAnalytics**: BI dashboards, predictive analytics, real-time monitoring
11. **AdvancedNeuralNetwork**: Ensemble models, deep learning, anomaly detection

### Core Systems

- **LLMCouncil**: Multi-model decision making with sequential loading for RAM efficiency
- **Chairman**: Final decision validation for critical tasks
- **MemorySystem**: Short-term, long-term, and episodic memory storage
- **TaskDecomposer**: Complex task breakdown into executable steps
- **AutonomyEngine**: LLM-optional autonomous planning
- **ToolRegistry**: Available tool management and discovery

### Session Memory Continuity (audited 2026-08-23 — honest capabilities)

What works today:
- **Within one running session**, ASC remembers: the last command and strategy (`last_command`, `last_strategy` short-term keys), pending items awaiting confirmation tokens (dangerous-command confirmations, form submissions, clarifications), and the last ~8 conversation turns. Conversation replies reference earlier chat turns correctly (verified live).
- Recent context is fed into autonomous planning via `_build_autonomy_context()` → `recent_context`, so plans can be influenced by what you just did.
- Session activity logs persist to `data/sessions.json`.

Honest limitations:
- **Short-term memory is in-RAM only.** Restarting `python main.py` forgets everything conversational; only long-term preferences and learning data survive restarts.
- Short-term memory TTL is stored but **not enforced** — entries expire only when the 100-entry ring buffer wraps.
- Non-conversation commands do not inject conversation history into their execution; continuity across command *types* is limited to planning context, not reply content.
- The conversation history lives inside the ConversationAgent instance, not persisted per-session on disk.


### Learning Pipeline

- **Phase 4**: Semi-supervised learning from user feedback
- **Phase 5**: Neural network-based route classification with PyTorch
- **AdaptiveLearningEngine**: Experience replay and reward modeling
- **NeuralCommandModel**: Confidence-based route predictions

## 🔧 Installation

### Prerequisites

- Python 3.13 or higher
- Ollama (optional but recommended for full functionality)
- Chromium browser (for web automation)
- Outlook (for Windows calendar integration, optional)

### Install Dependencies

```bash
# Clone the repository
git clone https://github.com/yourusername/AGI-System.git
cd AGI-System

# Install Python dependencies
pip install -r requirements.txt

# Install Ollama models (optional but recommended)
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull llava:7b
ollama pull gemma2:2b
ollama pull tinyllama

# Install Playwright for browser automation
playwright install chromium
```

### Optional Setup

#### Email Configuration
```bash
# Configure email sending (optional)
# See Configuration section for details
```

#### Calendar Integration
```bash
# Configure Google Calendar (optional)
# See Configuration section for details
```

#### External APIs
```bash
# Configure external API keys (optional)
# See Configuration section for details
```

## 🎯 Quick Start

### Basic Usage

```bash
# Start the interactive console
python main.py
```

### Example Commands

```bash
# Conversation
"Hello Jarvis, how are you?"
"What can you do?"

# System Operations
"Show system status"
"List running processes"
"Check disk usage"

# Task Management
"Create task: Prepare presentation, priority: high, due_date: 2026-09-14"
"List tasks"
"Daily plan"

# Project Management
"Create project: Website Redesign, end_date: 2026-09-30"
"Project status: [project_id]"
"Create gantt chart for project: [project_id]"

# Web Automation
"Open chrome and search for autonomous AI"
"Navigate to https://example.com"

# File Operations
"List files in current directory"
"Create file: test.txt with content: Hello World"
"Search for files containing 'test'"

# Learning System
"Show adaptive learning"
"Show phase5 learning"
"Show workflow patterns"

# Business Intelligence
"Generate productivity report for the past 7 days"
"Create business intelligence dashboard"
"Show resource utilization for project: [project_id]"

# Team Collaboration
"Add team member: John Doe, email: john@example.com, role: developer"
"Create shared workspace: Development Team"
"List team members"
```

## 🎯 Features

### Business Automation

#### Task Management
- Create, update, and track tasks with priorities and due dates
- Task categorization and project assignment
- Time tracking and productivity metrics
- Task comments and collaboration

#### Project Management
- Project creation with timelines and milestones
- Gantt chart generation (ASCII and data formats)
- Resource allocation and utilization analysis
- Project progress tracking and reporting

#### Calendar Integration
- Multi-platform support: Windows (Outlook), Google Calendar, Apple Calendar
- Event scheduling and management
- Upcoming event retrieval
- Meeting agenda generation

#### Team Collaboration
- Team member management with roles and skills
- Shared workspaces for project collaboration
- Team notifications and task assignments
- Comment threads on tasks

### Analytics & Intelligence

#### Productivity Metrics
- Task completion rates and time tracking
- Productivity score calculation
- Priority and project distribution analysis
- Customizable reporting periods

#### Business Intelligence Dashboard
- Overall health score calculation
- Project and task completion tracking
- Resource utilization analysis
- Actionable business insights

#### External API Integrations
- Weather API integration for location-based information
- News API for topic-based news retrieval
- Stock market API for financial data
- Extensible framework for additional APIs

### Advanced Planning

#### Autonomous Planning
- Business-oriented planning for scheduling tasks
- Sequential multi-step planning ("and then", "after that")
- Goal-oriented planning ("to", "in order to")
- Proactive assistance based on context

#### Multi-Agent Coordination
- Sequential, parallel, and hierarchical coordination strategies
- Agent status monitoring and load balancing
- Workflow optimization based on agent capabilities
- Efficiency estimation for workflow planning

### Security & Safety

#### Dangerous Command Protection
- System power commands require explicit confirmation
- File deletion and destructive operations need approval
- Configurable dangerous patterns
- Multi-stage confirmation for critical operations

#### Advisory Learning Model
- Phase 5 neural predictions are advisory-only
- Learned behavior never bypasses safety checks
- Model promotion and rollback mechanisms
- Confidence thresholds for automatic execution

#### Secure Credential Management
- Email and API credentials require explicit configuration
- Never auto-fills sensitive information
- Configuration validation and testing
- Encrypted credential storage (production deployment)

### Advanced Enterprise Features

#### AI/ML Capabilities
- **Ensemble Models**: Random Forest, Gradient Boosting for improved predictions
- **Deep Learning**: PyTorch-based neural networks with custom architectures
- **Predictive Analytics**: Time series forecasting, trend analysis
- **Anomaly Detection**: Statistical and ML-based anomaly identification
- **Model Management**: Training, evaluation, saving, and loading models

#### Business Process Automation
- **ERP Integrations**: SAP, Oracle, and custom ERP system connections
- **CRM Integrations**: Salesforce, HubSpot, and custom CRM systems
- **Workflow Orchestration**: Cross-system workflow automation
- **Process Mining**: Pattern discovery from execution logs
- **Business Rules**: Automated decision-making with configurable rules

#### Enterprise Security
- **Multi-Tenant Support**: Complete tenant isolation and management
- **Role-Based Access Control**: Granular permissions and user roles
- **GDPR Compliance**: Data protection, consent management, right to deletion
- **Audit Trails**: Comprehensive logging of all system events
- **Data Encryption**: Encryption/decryption of sensitive data
- **Compliance Reporting**: Automated compliance report generation

#### Advanced Analytics
- **BI Dashboards**: Customizable business intelligence dashboards
- **Real-Time Monitoring**: System health and performance monitoring
- **Predictive Analytics**: ML-powered predictions and forecasts
- **Custom Reports**: Scheduled analytics report generation
- **Data Visualization**: Charts, tables, and KPI cards
- **Performance Metrics**: Comprehensive system and business metrics

### Phase 7: Advanced AGI Capabilities

#### Meta-Learning System
- **Learning Strategy Optimization**: Automatic hyperparameter tuning and strategy selection
- **Meta-Model Training**: MAML and Reptile meta-learning algorithms
- **Neural Architecture Search**: Automated model architecture discovery
- **Transfer Learning Optimization**: Enhanced knowledge transfer between domains
- **Learning Efficiency Analysis**: Comprehensive learning performance metrics

#### Self-Reflection System
- **Performance Analysis**: Comprehensive self-assessment of actions and decisions
- **Capability Gap Identification**: Automatic detection of improvement areas
- **Cognitive Bias Detection**: Identification and mitigation of decision biases
- **Self-Improvement Planning**: Autonomous generation of improvement strategies
- **Intelligence Tracking**: Continuous monitoring of overall system intelligence

#### Autonomous Goal System
- **Self-Directed Learning**: Automatic generation of learning objectives
- **Goal Decomposition**: Breakdown of complex goals into actionable steps
- **Priority-Based Scheduling**: Dynamic goal prioritization based on context
- **Motivation Management**: Internal drive and motivation tracking
- **Progress Tracking**: Automatic goal progress monitoring and adjustment

#### Concept Discovery System
- **Novel Concept Generation**: Autonomous invention of new problem-solving approaches
- **Pattern Recognition**: Automatic detection of patterns in data and behavior
- **Concept Combination**: Synthesis of multiple concepts into new approaches
- **Creative Problem Solving**: Generation of innovative solutions
- **Innovation History**: Tracking of all discovered concepts and innovations

#### Self-Programming System
- **Code Generation**: Autonomous code generation from specifications
- **Code Refactoring**: Automatic code improvement and optimization
- **Bug Fixing**: Autonomous detection and resolution of bugs
- **Code Integration**: Automatic integration of generated code into the system
- **Programming History**: Complete tracking of all programming changes

#### Algorithm Optimization System
- **Performance Profiling**: Comprehensive algorithm performance analysis
- **Algorithm Selection**: Automatic selection of optimal algorithms for tasks
- **Complexity Analysis**: Automatic analysis of algorithm complexity
- **Optimization Recommendations**: Data-driven algorithm improvement suggestions
- **Benchmarking**: Comparative performance analysis across algorithms

#### Self-Evolving Architecture
- **Capability Expansion**: Autonomous addition of new capabilities
- **Component Activation**: Dynamic activation of available components
- **Architecture Evolution**: Automatic system architecture improvement
- **Configuration Optimization**: Dynamic optimization of system configuration
- **Evolution Tracking**: Complete history of system evolution

#### Advanced Cognitive Architecture
- **Common Sense Reasoning**: Human-like understanding of everyday situations
- **Causal Reasoning**: Understanding of cause-effect relationships
- **Analogical Reasoning**: Problem-solving through analogies and metaphors
- **Abstract Reasoning**: High-level abstract thinking and problem-solving
- **Social Cognition**: Understanding of social situations and interactions
- **Meta-Cognition**: Thinking about own thinking processes

## ⚙️ Configuration

### Main Configuration File

Edit `config/settings.json` to customize the system:

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
  },
  "email": {
    "configured": false,
    "smtp_server": "",
    "smtp_port": 587,
    "email_address": "",
    "password": "",
    "use_tls": true
  },
  "google_calendar": {
    "configured": false,
    "api_key": "",
    "calendar_id": "primary"
  },
  "weather_api": {
    "api_key": ""
  },
  "news_api": {
    "api_key": ""
  },
  "stock_api": {
    "api_key": ""
  }
}
```

### Email Configuration

```python
# Configure email sending
from agents.business_agent import BusinessAgent

agent = BusinessAgent("./config/settings.json")

result = agent.configure_email(
    smtp_server="smtp.gmail.com",
    smtp_port=587,
    email_address="your@gmail.com",
    password="your_app_password",
    use_tls=True
)
```

### Google Calendar Configuration

```python
# Configure Google Calendar
result = agent.configure_google_calendar(
    api_key="your_api_key",
    calendar_id="primary"
)
```

## 📚 API Documentation

### Business Agent API

#### Task Management
```python
# Create task
agent.create_task(
    title="Task title",
    description="Task description",
    priority="high",  # high, medium, low
    due_date="2026-09-14",
    project_id="project_uuid",
    category="general"
)

# List tasks
agent.list_tasks(status="pending", priority="high", project_id="project_uuid")

# Update task status
agent.update_task_status(task_id="task_uuid", status="completed")
```

#### Project Management
```python
# Create project
agent.create_project(
    name="Project name",
    description="Project description",
    start_date="2026-09-01",
    end_date="2026-09-30"
)

# Get project status
agent.get_project_status(project_id="project_uuid")

# Create Gantt chart
agent.create_gantt_chart(project_id="project_uuid", output_format="visual")
```

#### Analytics
```python
# Calculate productivity metrics
agent.calculate_productivity_metrics(days=7)

# Generate productivity report
agent.generate_productivity_report(days=7, format="text")

# Create business intelligence dashboard
agent.create_business_intelligence_dashboard(days=30)
```

### Main Controller API

#### Command Processing
```python
from main import AutonomousSystemController

controller = AutonomousSystemController()

# Process command
result = await controller.process_command("create task: Prepare presentation")
```

## 🧪 Testing

### Run All Tests
```bash
python -m pytest tests -v
```

### Run Specific Test Categories
```bash
# Basic functionality tests
python -m pytest tests/test_basic.py -v

# Phase 6 business tests
python -m pytest tests/test_phase6_business.py -v

# Form fill integration
python -m pytest tests/test_form_fill_integration.py -v

# System agent Ollama tests
python -m pytest tests/test_system_agent_ollama.py -v
```

### Test Coverage
- **Total Tests**: 147
- **Passing**: 142
- **Skipped**: 5 (Ollama offline)
- **Coverage**: Comprehensive functionality testing

## 🚀 Deployment

### Local Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Run the system
python main.py
```

### Production Deployment

#### Environment Setup
```bash
# Set up production environment
export PYTHONPATH=/path/to/AGI-System
export ASC_CONFIG=/path/to/production_config.json
export ASC_DATA_DIR=/path/to/data
```

#### Service Configuration
```bash
# Run as a service (Linux)
sudo systemctl enable asc.service
sudo systemctl start asc.service

# Run as a service (Windows)
# Use Task Scheduler or NSSM to create a Windows service
```

#### Docker Deployment
```bash
# Build Docker image
docker build -t asc:latest .

# Run container
docker run -d -p 5000:5000 --name asc asc:latest
```

## 🔒 Security

### Security Features

1. **Dangerous Command Protection**
   - System power commands require explicit confirmation
   - File deletion and destructive operations need approval
   - Configurable dangerous patterns

2. **Advisory Learning Model**
   - Neural predictions are advisory-only
   - Learned behavior never bypasses safety checks
   - Confidence thresholds for automatic execution

3. **Secure Credential Management**
   - Email and API credentials require explicit configuration
   - Never auto-fills sensitive information
   - Encrypted credential storage (production)

4. **Confirmation-Based Critical Actions**
   - System power commands staged with confirmation tokens
   - Form submission requires verification
   - Destructive operations need explicit approval

### Security Best Practices

1. **Credential Management**
   - Store credentials in secure configuration files
   - Use environment variables for sensitive data
   - Regularly rotate API keys and passwords
   - Implement credential encryption in production

2. **Network Security**
   - Use HTTPS for external API calls
   - Implement rate limiting for API requests
   - Validate all external inputs
   - Use secure protocols for data transmission

3. **Access Control**
   - Implement role-based access control
   - Audit team member access and permissions
   - Regular security audits and penetration testing
   - Implement logging and monitoring

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Fork the repository
git clone https://github.com/yourusername/AGI-System.git
cd AGI-System

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests -v

# Run linting
flake8 agents/ core/ main.py
```

### Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by Jarvis from Iron Man
- Built with PyTorch, Ollama, and Playwright
- Powered by local LLMs for privacy and control

## 📞 Support

For support, questions, or contributions:
- **Issues**: [GitHub Issues](https://github.com/yourusername/AGI-System/issues)
- **Documentation**: [Full Documentation](docs/)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/AGI-System/discussions)

## 🗺️ Roadmap

### Completed (Phase 6)
- ✅ Business workflow automation
- ✅ Multi-platform calendar integration
- ✅ Advanced project management
- ✅ Business analytics and intelligence
- ✅ Team collaboration features
- ✅ External API integrations
- ✅ Comprehensive testing suite

### Future Enhancements
- 🔄 Mobile application
- 🔄 Cloud synchronization
- 🔄 Advanced AI models
- 🔄 Enterprise features
- 🔄 Plugin system

---

**Built with ❤️ for intelligent, local-first automation**