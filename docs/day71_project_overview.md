# KnowledgeAI - Day 71 Technical Overview

## Objective

Build a functioning local LLM application
with a backend, web interface and repeatable
verification.

## Components

1. FastAPI handles HTTP requests.
2. Pydantic validates chat input.
3. HTTPX connects to the local Ollama API.
4. Qwen3 0.6B generates AI responses.
5. Browser frontend displays conversations.

## Input Constraints

- Maximum message length: 2,000 characters
- Maximum conversation history: 10 messages
- Supported history roles: user and assistant
- Unexpected request fields are rejected

## Failure Handling

- Invalid input: HTTP 422
- Ollama connection failure: HTTP 503
- Ollama provider failure: HTTP 502
- Provider timeout: HTTP 504
- Invalid or empty AI answer: HTTP 502

## Test Evidence

Automated suite:
21 passing tests.

Real-model evaluation:
10 successful requests.
10 expected keyword matches.

The model may give inaccurate or incomplete
answers despite passing these initial checks.

## Local Environment

Model: qwen3:0.6b
Provider: Ollama
Backend: FastAPI

The model is downloaded separately through
Ollama and is not stored in this repository.

## Current Product Scope

This is a working local chat application.

It is not yet:
- A document knowledge base
- A RAG system
- A publicly hosted website
- A production authentication system

## Interview Demonstration

1. Introduce the project architecture.
2. Show the local web interface.
3. Ask a technical question.
4. Show conversation context.
5. Open Swagger API documentation.
6. Demonstrate automated test results.
7. Explain limitations and future RAG work.

## Next Engineering Milestones

Implement document ingestion, embeddings,
retrieval, source-grounded answers and
automated evaluations.

## Publication

Publish source code and documentation.

Do not publish local model files, credentials,
private user documents or generated reports.
