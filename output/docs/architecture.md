# AgentOS Technical Architecture

## Document Purpose

This document provides a detailed technical specification of the AgentOS system, covering the pipeline orchestration, agent interactions, data flow, and infrastructure components. It serves as a reference for developers, contributors, and system integrators.

## System Overview

AgentOS is a multi-agent AI software development platform that automates the end-to-end process of transforming a product goal described in plain English into a fully tested, documented software project. The system operates through a compiled LangGraph state machine that coordinates seven specialized AI agents through defined pipeline stages with conditional routing, recovery mechanisms, and human oversight.

## Core Components

### 1. Pipeline Orchestration Layer

The heart of AgentOS is the compiled LangGraph state machine defined in `graph.py`. This compiled graph manages the pipeline execution flow, including:

- **State Management**: Maintains pipeline state across all agents, including the current goal, generated plan, file layout, test suite, source code, review scores, and test results
- **Conditional Routing**: Three primary routing functions determine the next pipeline stage based on quality scores and test results:
  - `route_after_plan`: Evaluates plan quality and determines whether to proceed to architecture, restart the pipeline, or escalate
  - `route_after_review`: Routes based on reviewer scores (score < 30 → re-architecture, score 30-74 → re-code, score ≥ 75 → proceed to testing)
  - `route_after_test`: Determines next step based on test outcomes (failed → fixer, passed → human approval, restart, or escalation)
- **Recovery Mechanisms**: Supports up to 4 fix iterations per pipeline pass and up to 3 full pipeline restarts before human escalation
- **State Persistence**: Checkpoint JSON files saved to `checkpoints/` directory for pipeline recovery and resume capability

### 2. Agent Specialization Layer

Seven dedicated AI agents, each with a specific role and set of responsibilities:

| Agent | Role | Primary Functions |
|-------|------|-------------------|
| **Planner** | Goal Analysis | Input sanitization, development plan generation, requirement decomposition |
| **Architect** | System Design | File structure design, component API definition, module boundary determination, technology selection |
| **Test Writer** | Test-First Development | Pytest suite generation from architecture, test case design, coverage targeting |
| **Coder** | Implementation | Source code generation, following test-first principles, API implementation, utility functions |
| **Reviewer** | Quality Gate | 3-panel parallel review (quality, security, performance), score assignment, feedback generation |
| **Tester** | Verification | Docker sandboxed test execution, pass/fail determination, traceback collection, performance metrics |
| **Fixer** | Error Resolution | Code patching from test errors, fix cycle management, duplicate fix avoidance, iterative improvement |

### 3. Routing & Decision Logic

The pipeline employs sophisticated conditional routing based on numerical scores and boolean conditions:

#### Review Scoring System

The Reviewer agent assigns three independent scores:

- **Quality Score**: Assesses code maintainability, readability, and adherence to best practices
- **Security Score**: Evaluates vulnerability exposure, input validation, and potential attack vectors
- **Performance Score**: Measures efficiency, resource usage, and algorithmic complexity

Each score ranges from 0-100. The composite behavior:

- **Score < 30 in any category**: Triggers re-architecture or major code revision
- **Score 30-74**: Triggers code revision with specific feedback
- **Score ≥ 75 in all categories**: Proceeds to testing phase

#### Conditional Routing Functions

```python
# Simplified routing logic
def route_after_plan(plan_quality_score):
    if plan_quality_score < 30:
        return "restart"  # Re-generate development plan
    elif plan_quality_score < 75:
        return "proceed_with_feedback"  # Minor plan adjustments
    else:
        return "proceed"  # Continue to architect

def route_after_review(quality, security, performance):
    min_score = min(quality, security, performance)
    if min_score < 30:
        return "re_architecture"
    elif min_score < 75:
        return "re_code"
    else:
        return "proceed_to_test"

def route_after_test(test_passed, max_retries_exceeded):
    if not test_passed and max_retries_exceeded:
        return "escalate"  # Human intervention required
    elif not test_passed:
        return "fixer"  # Code patching cycle
    else:
        return "approve"  # Human approval or auto-approve
```

### 4. Multi-Provider LLM Routing

AgentOS implements a resilient multi-provider routing system configured in `config/models.yaml`:

#### Fallback Chain Configuration

Each agent role has an ordered fallback chain:

```yaml
models:
  planning:
    chain:
      - { provider: groq,        model: openai/gpt-oss-120b }
      - { provider: groq,        model: qwen/qwen3.8-27b }
      - { provider: openrouter,  model: inclusionai/ling-3.0-flash-sante:free }

  coding:
    chain:
      - { provider: groq,        model: openai/gpt-oss-120b }
      - { provider: openrouter,  model: cohere/north-mini-code:free }
```

#### Resilience Mechanisms

1. **Zero-Delay Failover**: On HTTP 429 (rate limit), immediately switch to next provider with 0.3s delay
2. **Adaptive Prompt Throttling**: On "request too large" responses, truncate prompt to 70% and retry
3. **Dynamic Retry-After Parsing**: Extract and honor provider-specified retry durations using regex
4. **Multi-Cycle Retries**: Up to 3 complete cycles through all providers before failure
5. **Emergency Bypass Mode**: Skip cloud APIs entirely for development/testing, synthesizing placeholder responses

### 5. Configuration Management

#### Model Routing — `config/models.yaml`

Defines provider chains per agent role. Editable via config file or Web UI Settings modal.

#### Thresholds — `config/thresholds.yaml`

Controls pipeline behavioral parameters:

```yaml
review:
  min_score: 75           # Minimum composite score to pass review
  low_score_arch: 30      # Score threshold triggering re-architecture

loop:
  max_iterations: 4       # Fix iterations per pipeline pass
  max_global_iterations: 3  # Full pipeline restarts before escalation

docker:
  image: "python:3.11-slim"
  timeout_seconds: 120
  memory_limit: "512m"
  network: "none"
```

## Data Flow Architecture

### Pipeline Execution Flow

```
1. USER INPUT → PLANNER → 2. ARCHITECT → 3. TEST WRITER → 4. CODER →
5. REVIEWER → [Routing Decision] → 6. TESTER → [Test Result] →
7. [Pass/Fail Decision] → 8. FIXER (if failed) → Loop back to Tester →
9. [Final Pass] → HUMAN APPROVAL → 10. OUTPUT GENERATION
```

### State Transition Diagram

```
┌─────────────────┐
│   INITIAL STATE   │
└───────┬───────────┘
        │
        ▼
┌─────────────────┐
│   PLANNER STAGE   │  → Generate development plan
└───────┬───────────┘
        │
        ▼
┌─────────────────┐
│   ARCHITECT STAGE │  → Design file layout & APIs
└───────┬───────────┘
        │
        ▼
┌─────────────────┐
│ TEST WRITER STAGE│  → Generate pytest suite
└───────┬───────────┘
        │
        ▼
┌─────────────────┐
│     CODER STAGE  │  → Implement source code
└───────┬───────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│   REVIEWER STAGE (3 parallel panels)              │
│   Quality | Security | Performance                 │
│   Scores: 0-100 each                               │
└───────┬─────────────────────────────────────────────┘
        │  Based on scores:                             │
        ▼                                           │
┌─────────────────────────────────────────────────┐
│   ROUTING DECISION                              │
│  ├─ Score < 30 → Return to Architect            │
│  ├─ Score 30-74 → Return to Coder               │
│  ├─ Score ≥ 75 → Proceed to Tester              │
│  └─ All ≥ 75 → Proceed to Tester                │
└───────┬─────────────────────────────────────────┘
        │                                           │
        ▼                                           ▼
┌─────────────────┐                                    ┌─────────────────┐
│   TESTER STAGE  │                                    │   FIXER STAGE   │
│   Docker sandbox│                                    │   Code patching │
│   Test execution│                                    │   Error repair  │
└───────┬─────────┘                                    └───────┬─────────┘
        │                                                  │
    Passed?                                              Tests failed?
        │                                                  │
        ├─── Yes ──► Human approval gate                    ── No ────┤
        │                                              │
        ▼                                              ▼
┌─────────────────┐                                    ┌─────────────────┐
│   OUTPUT STAGE  │                                    │   RESTART       │
│   Generated     │                                    │   Pipeline      │
│   artifacts     │                                    │   restart       │
└─────────────────┘                                    └─────────────────┘
```

### Agent Communication Patterns

#### Unidirectional Flow

The pipeline follows a unidirectional data flow pattern:

1. **Input → Planner**: User goal → sanitized plan
2. **Planner → Architect**: Plan → file layout and API specifications
3. **Architect → Test Writer**: Design → test suite requirements
4. **Test Writer → Coder**: Test suite → implementation specifications
5. **Coder → Reviewer**: Source code → quality evaluation
6. **Reviewer → Router**: Code + scores → routing decision
7. **Router → Tester**: Decision + code → test execution
8. **Tester → Fixer (if failed)**: Test results → error patches
9. **Fixer → Coder (loop)**: Patches → updated code
10. **Tester → Output (if passed)**: Results → final deliverables

#### Shared State

All agents operate on a shared Python dictionary state object that persists throughout the pipeline execution. Key state keys include:

- `goal`: Original user goal statement
- `plan`: Generated development plan
- `file_layout`: Designed file structure
- `test_suite`: Generated pytest code
- `source_code`: Implemented source files
- `review_scores`: Three-panel review scores
- `test_results`: Pass/fail status and tracebacks
- `iteration_count`: Current fix/test iteration count
- `pipeline_status`: Current stage enumeration

## Infrastructure Architecture

### Containerized Test Execution

AgentOS employs Docker-based sandboxed test execution as the default, with host fallback:

#### Docker Sandbox Configuration

```yaml
docker:
  image: "python:3.11-slim"
  timeout_seconds: 120
  memory_limit: "512m"
  network: "none"
```

**Sandbox Features**:
- Isolated Python runtime environment
- Disabled network access prevents external connectivity
- 512 MB memory limit prevents resource exhaustion
- 120-second timeout per test execution
- Automatic fallback to host execution if Docker unavailable

#### Host Fallback Execution

When Docker is unavailable, AgentOS falls back to isolated host execution:

- Uses custom `agentos_pytest.ini` configuration
- Prevents interference with host's `pyproject.toml`
- Installs dependencies in isolated environment
- Collects and reports test results with full tracebacks

### API Server Architecture

The FastAPI-based web server (`api.py`) provides:

- **WebSocket Streaming**: Real-time pipeline stage streaming to web UI
- **REST Endpoints**: CLI and web UI interaction endpoints
- **Session Management**: Pipeline session creation, status tracking, and checkpoint retrieval
- **Artifact Serving**: Generated file delivery and download

### Web UI Architecture

The React + Vite frontend (`frontend/`) features:

- **Component Library**: Reusable UI components for pipeline viewing, artifact browsing, and settings
- **WebSocket Integration**: Live connection to backend for real-time updates
- **State Management**: Local state with WebSocket-synchronized data
- **Dark Mode**: Complete dark-mode design system using CSS variables
- **Responsive Layout**: Mobile-friendly interface for dashboard and settings

### Rate Limit Bypass Infrastructure

The router subsystem (`router/`) implements comprehensive resilience:

```python
# Simplified fallback chain execution
def execute_with_fallback(prompt, provider_chain, max_cycles=3):
    for cycle in range(max_cycles):
        for provider_info in provider_chain:
            try:
                response = call_llm(provider_info, prompt)
                return response  # Success - return immediately
            except RateLimitError:
                wait_time = extract_retry_after(provider_info) or 0.3
                time.sleep(wait_time)
            except TooLargeError:
                truncated_prompt = truncate_prompt(prompt, 0.7)
                continue  # Retry with truncated prompt
            except Exception:
                continue  # Try next provider
    raise AllProvidersExhaustedError
```

## Security Architecture

### Input Sanitization

- **Planner Agent**: Sanitizes and validates user goal input before processing
- **Pydantic Schemas**: All API endpoints use Pydantic for request/response validation
- **Type Hinting**: Complete type hints throughout the codebase for static analysis

### Sandbox Isolation

- **Docker Network**: `none` mode prevents container internet access
- **File System**: Limited container filesystem access
- **Process Isolation**: Test execution runs as separate process

### Dependency Management

- **Pinned Versions**: `requirements.txt` with exact version specifications
- **Regular Scanning**: CI integrates `bandit` (security) and `safety` (vulnerability) scans
- **Lock Files**: `requirements.txt` generated from locked dependencies

## Extensibility Points

### Adding New Agents

1. Create new agent module in `agents/` directory
2. Implement standardized interface methods:
   - `execute(state: dict) → dict`
   - `validate_input(input_data) → bool`
3. Register agent in `graph.py` state machine
4. Add routing logic if needed

### Customizing Pipeline Behavior

1. Modify `config/thresholds.yaml` for score thresholds
2. Update `config/models.yaml` for provider chains
3. Adjust Docker settings in thresholds configuration
4. Extend routing functions in `graph.py`

### Provider Integration

1. Add provider configuration to `config/models.yaml`
2. Ensure provider SDK is in `requirements.txt`
3. Test fallback chain behavior
4. Update rate limit handling if needed

## Monitoring & Observability

### Pipeline Logging

- **Rich Console**: Colored terminal output with rich formatting
- **WebSocket Logs**: Real-time streaming to web UI
- **Checkpoint Snapshots**: JSON state dumps at each pipeline stage
- **Error Classification**: Automatic error type identification and handling

### Performance Metrics

- **Token Usage**: Per-agent token consumption tracking
- **Execution Time**: Stage-wise timing measurements
- **Retry Counts**: Number of fix/restart iterations
- **Provider Utilization**: Fallback chain usage statistics

### Diagnostic Reports

On pipeline completion or escalation, AgentOS generates:
- Execution summary with timing
- Agent contribution report
- Failure analysis (if applicable)
- Recommendations for future runs

## Deployment Architecture

### Production Considerations

1. **API Key Management**: Secure storage and rotation of LLM API keys
2. **Docker Resource Limits**: Appropriate memory/CPU limits for sandbox containers
3. **Rate Limit Monitoring**: Track provider usage patterns and adjust chains
4. **Human Approval Workflow**: SLA for approval gate turnaround
5. **Output Backup**: Regular backup of generated `output/` directory

### Scaling Options

- **Multiple Instances**: Horizontal scaling of AgentOS server
- **Provider Pooling**: Distribute load across multiple API key sets
- **Queue Management**: Pipeline execution queue for burst traffic
- **Caching**: Cache common plan/architecture patterns

## Future Roadmap Enhancements

Planned architecture improvements include:

1. **Microservice Decomposition**: Split agents into independent services
2. **Advanced Caching**: Semantic cache for similar goals/architectures
3. **Multi-Language Support**: Extend beyond Python to JavaScript, Java, etc.
4. **CI/CD Integration**: Direct GitHub Actions integration
5. **Enhanced Diagramming**: Graph visualization of pipeline state
6. **Audit Logging**: Comprehensive activity logging for compliance
7. **Collaborative Mode**: Human-in-the-loop at multiple stages simultaneously
8. **Plugin Architecture**: Extensible agent plugin system