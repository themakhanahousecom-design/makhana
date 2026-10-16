import json
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory


def test_document_data_and_summary_commands_stay_local(tmp_path):
    (tmp_path/'report.txt').write_text('Revenue increased. Revenue and sales are reported. Expenses stayed stable.', encoding='utf-8')
    (tmp_path/'data.csv').write_text('name,value\none,2\ntwo,4\n', encoding='utf-8')
    class NoWindows:
        def launch(self, name):
            raise AssertionError('Local document data cannot invoke an app')
    settings = Settings(approved_folders=[str(tmp_path)])
    engine = Engine(settings, Memory(tmp_path/'notes.db'), NoWindows())
    preview = engine.execute('document report.txt')
    summary = engine.execute('summarize file report.txt')
    csv = engine.execute('analyze csv data.csv')
    assert preview.ok and 'Revenue' in preview.message
    assert summary.ok and 'Local extractive summary' in summary.message
    assert csv.ok and json.loads(csv.message)['row_count'] == 2
    assert not engine.memory.path.exists()
    assert not engine.ai._turns


def test_local_document_workflow_does_not_require_ai_provider(tmp_path):
    (tmp_path/'report.txt').write_text('A local document. Another local sentence.', encoding='utf-8')
    settings = Settings(approved_folders=[str(tmp_path)], workflows={'read report': ['document report.txt', 'summarize file report.txt']})
    engine = Engine(settings, Memory(tmp_path/'notes.db'))
    result = engine.execute('run workflow read report')
    assert result.ok and 'Local extractive summary' in result.message


def test_document_errors_keep_correct_tool_category(tmp_path):
    engine = Engine(Settings(approved_folders=[str(tmp_path)]), Memory(tmp_path/'notes.db'))
    result = engine.execute('document missing.pdf')
    assert not result.ok and result.agent == 'Documents'
    result = engine.execute('analyze csv missing.csv')
    assert not result.ok and result.agent == 'Data Analysis'
