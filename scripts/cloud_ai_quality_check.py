"""Bounded live tests using synthetic inputs only. Run from repository root."""
import getpass
import json
import math
import re
from backend.cloud_ai import CloudAI, CloudAIError

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}, "source": {"type": "string", "enum": ["S1"]}}, "required": ["answer", "source"], "additionalProperties": False}

def main():
    if input('Confirm Workers Free plan (type FREE): ').strip() != 'FREE':
        return 1
    account = input('Cloudflare Account ID: ').strip()
    token = getpass.getpass('Workers AI API token (hidden): ').strip()
    try:
        ai = CloudAI(account, token)
    except ValueError as exc:
        print('STOP:', exc)
        return 1
    checks = []
    def check(name, fn):
        try:
            passed = bool(fn())
        except (CloudAIError, ValueError) as exc:
            print(name + ': ERROR -', exc)
            if any(f'HTTP {status}' in str(exc) for status in (401, 403, 429)):
                raise
            passed = False
        checks.append(passed)
        print(name + ':', 'PASS' if passed else 'REVIEW')

    def chat():
        reply = ai.chat([{'role':'system','content':'You are a concise educational assistant. Do not repeat yourself.'}, {'role':'user','content':'In one short sentence, explain the purpose of a database.'}], max_tokens=80)
        print('Chat answer:', reply)
        sentences = [s.strip().lower() for s in re.split(r'[.!?\n]+', reply) if s.strip()]
        return bool(re.search(r'\b(stor\w*|organiz\w*|manag\w*|retriev\w*)\b',reply,re.I)) and len(reply.split()) <= 40 and len(sentences) == len(set(sentences)) and len(sentences) <= 2

    def grounded():
        reply = ai.chat([{'role':'system','content':'Answer using only the supplied source. Return a JSON object with answer and source.'}, {'role':'user','content':'Source S1: The synthetic office opens at 9 AM. Question: When does the office open?'}], max_tokens=256, json_schema=SCHEMA)
        print('Grounded JSON answer:', reply)
        obj = json.loads(reply)
        return set(obj) == {'answer','source'} and isinstance(obj['answer'],str) and bool(re.search(r'\b9\s*(?::00)?\s*a\.?m\.?',obj['answer'],re.I)) and obj['source'] == 'S1'

    def semantic():
        vectors = ai.embed(['A database stores structured records.','A database saves and retrieves data.','Bananas are yellow tropical fruits.'])
        def cosine(a,b): return sum(x*y for x,y in zip(a,b))/(math.hypot(*a)*math.hypot(*b))
        near,far = cosine(vectors[0],vectors[1]),cosine(vectors[0],vectors[2])
        print(f'Embedding similarity: related={near:.4f}, unrelated={far:.4f}')
        return near > far
    try:
        check('Concise chat heuristic', chat)
        check('Grounded JSON heuristic', grounded)
        check('Semantic ranking', semantic)
    except CloudAIError:
        print('STOP: Authentication, permission or rate limit failure; no further requests.')
        return 1
    passed = len(checks) == 3 and all(checks)
    print('CLOUD PROVIDER QUALITY CHECK:', 'PASS' if passed else 'REVIEW NEEDED')
    return 0 if passed else 2

if __name__ == '__main__':
    raise SystemExit(main())
