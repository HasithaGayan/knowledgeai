"""Persistent limits; fixed global buckets avoid unbounded keys from strangers."""
from datetime import datetime, timezone

class CloudLimitExceeded(Exception):
    pass

class CloudLimits:
    def __init__(self, store):
        self.store = store

    def migrate(self):
        with self.store.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(821642905)')
            conn.execute('''CREATE TABLE IF NOT EXISTS knowledgeai_v1.request_budgets (
                bucket varchar(100) NOT NULL, period date NOT NULL,
                used integer NOT NULL CHECK(used > 0), PRIMARY KEY(bucket, period))''')

    def consume(self, category, owner=None, units=1):
        # Conservative application request limits, not a provider neuron measurement.
        if category == 'auth':
            if owner is not None or units != 1:
                raise ValueError('Invalid auth budget')
            buckets = [('auth-global', 120)]
        elif category == 'register':
            if owner is not None or units != 1:
                raise ValueError('Invalid registration budget')
            buckets = [('register-global', 12)]
        elif category == 'ai' and owner is not None and units in (1, 2, 4):
            buckets = [('ai-global', 40), ('ai-user:' + str(owner), 12)]
        else:
            raise ValueError('Invalid budget')
        today = datetime.now(timezone.utc).date()
        with self.store.connect() as conn:
            for bucket, limit in buckets:
                row = conn.execute('''INSERT INTO knowledgeai_v1.request_budgets(bucket,period,used)
                    VALUES (%s,%s,%s) ON CONFLICT (bucket,period) DO UPDATE
                    SET used=knowledgeai_v1.request_budgets.used+EXCLUDED.used
                    WHERE knowledgeai_v1.request_budgets.used+EXCLUDED.used<=%s
                    RETURNING used''', (bucket,today,units,limit)).fetchone()
                if row is None:
                    # Entire transaction rolls back, including any previous bucket.
                    raise CloudLimitExceeded()
