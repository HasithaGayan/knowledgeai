# KnowledgeAI

A local AI chat application powered by Qwen3,
Ollama, Python and FastAPI.

## Overview

KnowledgeAI demonstrates how a local language
model can be integrated into a real web application.

The application provides an interactive chat
interface, server-side AI inference, conversation
context and API error handling.

No paid AI API key is required.

## Features

- Responsive browser-based chat interface
- Local Qwen3 0.6B language model
- FastAPI backend
- REST API integration with Ollama
- Conversation context (up to 10 messages)
- Input validation
- Model health checking
- Provider timeout and error handling
- Automated API and frontend tests
- Repeatable real-model prompt evaluations

## Technology

Backend:
- Python
- FastAPI
- Pydantic
- HTTPX

Frontend:
- HTML
- CSS
- JavaScript

AI:
- Ollama
- Qwen3 0.6B

Testing:
- Pytest
- FastAPI TestClient

## Architecture

Browser chat interface
        |
        v
FastAPI backend
        |
        v
Ollama local API
        |
        v
Qwen3 language model
        |
        v
AI-generated response

## Installation

1. Install Python and Ollama.

2. Download the local AI model:

       ollama pull qwen3:0.6b

3. Create a Python virtual environment:

       python -m venv .venv

4. Install dependencies:

       .venv\Scripts\python.exe -m pip install -r requirements.txt

5. Ensure Ollama is running locally.

6. Start KnowledgeAI:

       .venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001

7. Open:

       http://127.0.0.1:8001/chat

If port 8001 is occupied, choose another
available port, such as 8002.

## API Endpoints

GET /                 Application information
GET /chat             Chat website
GET /api/health       Local model health
POST /api/chat        AI chat requests
GET /docs             Interactive API documentation

## Testing

Run automated tests:

    .venv\Scripts\python.exe -m pytest tests -q

Day 71 result: 21 tests passed.

## Real Model Evaluation

Run the evaluation while the API is
available at http://127.0.0.1:8001:

    .venv\Scripts\python.exe tests/day71_prompt_eval.py

The initial evaluation completed 10 successful
real-model requests with 10 expected keyword
matches.

Keyword matching alone does not establish
complete factual correctness.

## Security and Privacy

- Local development server binds to 127.0.0.1.
- Ollama runs on the local machine.
- No hosted AI API key is required.
- Python environments and generated reports
  are excluded from Git.
- The AI model itself is not committed.
- Chat messages are not saved to a server-side
  conversation database by this version.

The application has no user authentication
or production-grade rate limiting. Do not
expose this development server publicly.

## Current Limitations

- Uses a small experimental language model.
- Answers can contain factual mistakes.
- Document upload and RAG are not implemented yet.
- Chat history is not permanently saved.
- No public deployment currently exists.

## Future Development

- Document upload and parsing
- Semantic retrieval
- Retrieval-Augmented Generation
- Source citations
- Stronger answer evaluations
- Deployment preparation

## Project Documentation

See docs/day71_project_overview.md

## Status

Day 71: Local AI chat MVP.

Educational AI engineering portfolio project.

## Day 72 - Document Studio and Structured Answers

KnowledgeAI now provides:

- TXT and Markdown document upload and preview.
- Text extraction and document chunking.
- Source and chunk metadata.
- Structured AI answers with application validation.
- Error handling for invalid AI output.
- Automated API and component tests.

### Local Pages

Document Studio:

    http://127.0.0.1:8002/documents

Structured Answers:

    http://127.0.0.1:8002/structured

The port depends on the local server configuration.

### Scope and Limitations

Document Studio currently processes TXT/Markdown files.
Uploaded documents are not connected to the AI answer
generation pipeline yet.

PDF support, semantic retrieval, RAG citations and
public deployment are future milestones.

### Verification

    python -m pytest tests -q

Day 72 checkpoint: 65 passing automated tests.
