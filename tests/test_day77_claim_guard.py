import pytest
from backend.answer_guard import is_answer_consistent_with_quote as agrees

FEE = 'The workshop fee is LKR 2500.'

@pytest.mark.parametrize('a,q,want', [
    ('The AI workshop is free.',FEE,False),
    ('The AI workshop is completely free.',FEE,False),
    ('There is no fee.',FEE,False),
    ('It costs nothing.',FEE,False),
    ('The fee is LKR 3000.',FEE,False),
    ('The fee is 3000.',FEE,False),
    ('The fee is LKR 2500.',FEE,True),
    ('It is not free. The workshop costs LKR 2500.',FEE,True),
    ('It is not completely free.',FEE,True),
    ('It is a paid workshop.',FEE,True),
    ('The location is Room B12.','The venue is Room B12.',True),
    ('','The venue is Room B12.',False),
    ('It is free.','There is no charge.',True),
])
def test_claim_guard(a,q,want):
    assert agrees(a,q) is want
