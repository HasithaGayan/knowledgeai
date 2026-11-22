# KnowledgeAI — Day 77 Groundedness Evaluation

## Objective
Evaluate local document Q&A accuracy, source evidence,
appropriate abstention, and misleading-question handling.

## Evaluation environment
- Local FastAPI document Q&A application
- Ollama model: qwen3:0.6b
- Semantic retrieval using all-minilm
- Three fictional documents in an isolated workspace
- Twenty-five predefined evaluation questions

## Results

| Category | Passed | Total |
|---|---:|---:|
| Direct factual questions | 12 | 12 |
| Paraphrased questions | 4 | 5 |
| Misleading questions | 1 | 3 |
| Missing-information questions | 5 | 5 |
| **Total** | **22** | **25** |

Observed score: 88% (22/25).

Prior observed scores:
- Initial: 72% (18/25)
- Intermediate: 84% (21/25)
- Latest: 88% (22/25)

## Automated verification
- 270 automated tests passed.
- One non-blocking Starlette deprecation warning.

## Improvements
- Conservative claim contradiction checks.
- Evidence quote alignment.
- Narrow grounded fact recovery.
- Numeric answer unit completion.
- Safer citation fallback behavior.
- Repeatable 25-question evaluation harness.

## Known failures
1. Saturday library opening time: false abstention.
2. Workshop free/paid question: false abstention.
3. Upload permission for a 20 MB project: false abstention.

## Important limitations
- These results apply only to the synthetic evaluation set.
- The checks do not establish general factual reliability.
- Citation presence alone is not proof of semantic correctness.
- The extractive recovery logic handles limited patterns.
- The application remains a local prototype, not a
  production-ready publicly authenticated service.
- Real-model behavior may vary across evaluation runs.

## Next priorities
- Investigate remaining false abstentions.
- Expand evaluation with diverse real-world-style documents.
- Test conflicting evidence and prompt injection.
- Review security, privacy, authentication, and deployment
  readiness before making the service publicly accessible.

## Evaluation artifacts
Generated JSON reports are stored locally under
reports/generated/day77/ and excluded from Git.
