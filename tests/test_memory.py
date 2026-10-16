import pytest
from sidhu.memory import Memory


def test_edit_search_delete_survive_reopen(tmp_path):
    path = tmp_path / 'notes.db'
    memory = Memory(path)
    memory.add('Initial note')
    memory.add('Unrelated')
    memory.update(1, 'Updated project preference')
    reopened = Memory(path)
    assert reopened.search('PROJECT') == [(1, 'Updated project preference')]
    reopened.delete(1)
    assert Memory(path).list() == [(2, 'Unrelated')]


def test_memory_queries_treat_sql_as_data(tmp_path):
    memory = Memory(tmp_path / 'notes.db')
    memory.add("quote ' OR 1=1 --")
    memory.add('ordinary')
    assert len(memory.search("' OR 1=1 --")) == 1
    assert memory.search("' UNION SELECT 1 --") == []
    assert len(memory.list()) == 2


def test_missing_note_and_empty_edit_report_errors(tmp_path):
    memory = Memory(tmp_path / 'notes.db')
    with pytest.raises(ValueError):
        memory.update(999, 'text')
    with pytest.raises(ValueError):
        memory.delete(999)
    memory.add('original')
    with pytest.raises(ValueError):
        memory.update(1, '   ')
    assert memory.list() == [(1, 'original')]
