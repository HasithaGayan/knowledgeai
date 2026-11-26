"""Run bounded real-model integration tests on fictional documents only.
No local DB reads, no report files, no persistent credentials. One run sends
3 document embedding requests, 2 general generation requests, and 8 pairs
of query embedding + RAG requests. Never retry automatically.
"""
import getpass
from backend.cloud_ai import CloudAI, CloudAIError
from backend.cloud_core import CloudCore
from scripts.day77_evaluate_25 import DOCUMENTS, CASES, score_case


def main():
    if input('Confirm Workers Free plan (type FREE): ').strip() != 'FREE':
        print('STOP: Free plan not confirmed.')
        return 1
    account = input('Cloudflare Account ID: ').strip()
    token = getpass.getpass('Workers AI API token (hidden): ').strip()
    try:
        core = CloudCore(CloudAI(account, token))
        print('=== CORE INTEGRATION: FICTIONAL DATA ONLY ===')
        chat = core.chat('In one sentence, explain what SQL is.')
        chat_ok = bool(chat['answer'].strip()) and 'sql' in chat['answer'].lower()
        print('Chat:', 'PASS' if chat_ok else 'REVIEW')
        structured = core.structured('What is a primary key in a database?')
        structured_ok = structured['status'] == 'answered' and structured['source_status'] == 'no_document_sources'
        print('Structured answer:', 'PASS' if structured_ok else 'REVIEW')
        chunks = []
        for name, doc in DOCUMENTS.items():
            chunks.extend(core.index_document(name, doc.encode('utf-8')))
        print(f'Indexed {len(DOCUMENTS)} fictional documents, {len(chunks)} chunks (memory only)')
        cases = [case for case in CASES if case.number in {1,2,8,15,18,19,21,25}]
        passed = 0
        for case in cases:
            result = core.ask(case.question, chunks)
            ok, reason = score_case(case, result)
            passed += int(ok)
            print(f'Case {case.number:02d} [{case.category}]: {"PASS" if ok else "REVIEW"} — {reason}')
            print('  Answer:', result['answer'])
            for source in result['sources']:
                print('  Source:', source['source'], '|', source['evidence_quote'])
        print(f'RAG SCORE: {passed}/{len(cases)}')
        ok = chat_ok and structured_ok and passed == len(cases)
        print('CLOUD CORE EVALUATION:', 'PASS' if ok else 'REVIEW NEEDED')
        return 0 if ok else 2
    except (CloudAIError, ValueError) as exc:
        print('STOP:', str(exc))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
