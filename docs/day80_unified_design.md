# KnowledgeAI — Unified interface (Day 80)

A consistent visual layer has been applied to the existing KnowledgeAI pages.
The original `/workspace` page remains the design reference and is not changed.

## Design system

- Deep forest-green workspace navigation across all pages
- Custom KnowledgeAI book-and-code mark, warm ivory backdrop, copper headings, soft-gold accents
- Matching cards, button hierarchy, document citations and form controls
- Collapsible mobile navigation with visible keyboard focus and reduced-motion support
- Existing form IDs, JavaScript event handlers and backend functionality preserved

## Routes

`/workspace`, `/chat`, `/rag`, `/conversations`, `/documents`, `/structured`, `/tools`, `/agent`, `/evaluation`, `/privacy`

## Verification

Run `.\.venv\Scripts\python.exe -m pytest -q` and use the local website to verify each page manually.
Visual review on different screen widths remains required.

## Limitations

This changes presentation only. KnowledgeAI remains a single-computer prototype without production authentication, comprehensive security, or guaranteed semantic accuracy. No hosted service is created by this package.
