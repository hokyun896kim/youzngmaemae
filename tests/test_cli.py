"""CLI 모듈이 불러와지고 명령이 등록돼 있는지 (문법 오류를 테스트 단계에서 잡기 위함)."""
import pytest

from yujeung import cli


def test_cli_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ("daily", "backfill-cases", "report-case", "verify", "export"):
        assert cmd in out
