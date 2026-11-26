# KnowledgeAI

An intelligent cloud workspace for document intelligence,
AI conversations and human-approved report generation.

## Live Application

https://knowledgeai-flame.vercel.app/

## Features

- Account registration and authentication
- Personal document library
- TXT and Markdown document indexing
- Retrieval-Augmented Generation (RAG)
- Answers with supporting source passages
- General AI chat
- Structured AI answers
- Persistent private conversations
- Agent Studio report generation
- Human approval before report export
- Markdown report downloads
- Responsive desktop and mobile interface

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Database | Neon PostgreSQL |
| AI | Cloudflare Workers AI |
| Embeddings | BGE Small English |
| Validation | Pydantic |
| Hosting | Vercel |
| Testing | Pytest |

## Architecture

Browser -> Vercel HTTPS -> FastAPI

FastAPI -> Neon PostgreSQL
FastAPI -> Cloudflare Workers AI

## Engineering Highlights

- Semantic document retrieval
- Account-scoped data storage
- Persistent conversation context
- Restricted database permissions
- AI usage controls
- Approval-gated agent workflows
- Deterministic report calculations

## Verification

- Document indexing and retrieval tested
- Source-supported answers tested
- Conversation memory tested
- Agent generation and approval tested
- Browser account isolation tested
- Production HTTP endpoint checks passed
- Production AI response verified

## Privacy and Limitations

KnowledgeAI is a limited-capacity public cloud beta.

Use non-sensitive information only.
Consented content is processed by Cloudflare Workers AI.
Workspace data is stored in Neon PostgreSQL.
AI-generated answers may contain inaccuracies.

Email verification, password recovery and account deletion
are not yet available.

Full security auditing, large-scale load testing and
database restoration drills remain outstanding.

## Local Development History

The original Ollama-based implementation is preserved.

See [Local Version History](docs/local-version-history.md).

## Developer Portfolio

https://hasithagayan.github.io/ai-fullstack-87/

Developed as part of the HGBP AI and Full-Stack
Engineering Roadmap.
