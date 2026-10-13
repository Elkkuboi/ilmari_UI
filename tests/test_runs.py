"""Independent filesystem fixtures exercise reads and publication boundaries."""

import json
import os
from pathlib import Path

import pytest

from ilmari_ui import runs
from ilmari_ui.runs import ReadFailure, RunReader

RUN = "20261013-001914-yo-q6"
OTHER_RUN = "20261012-225008-yo-q6"


@pytest.fixture
def publication(tmp_path: Path) -> Path:
    root = tmp_path / "ajot"
    run = root / RUN
    run.mkdir(parents=True)
    # These are explicitly test fields, not a claim about the inaccessible
    # upstream MUODOT.md semantics. The reader must not infer statuses.
    (run / "meta.json").write_text('{"test_source":"independent fixture","count":2}', encoding="utf-8")
    (run / "raportti.md").write_text("# Raportti\n<script>alert('test')</script>\n", encoding="utf-8")
    (run / "ehdotukset.jsonl").write_text('{"test_title":"Ensimmäinen"}\n{"test_title":"Toinen"}\n', encoding="utf-8")
    (run / "sol-tulos.json").write_text('{"test_results":[{"test_verdict":"T"}]}', encoding="utf-8")
    (run / "luonnos.patch").write_text("--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-old\n+new\n", encoding="utf-8")
    return root


def test_success_preserves_plain_text_and_json(publication):
    reader = RunReader(publication)
    listed = reader.list_runs()
    assert listed.state == "ready"
    assert listed.errors == ()
    assert listed.runs[0].run_id == RUN
    assert listed.runs[0].title == RUN
    assert listed.runs[0].meta == {"test_source": "independent fixture", "count": 2}
    detail = reader.read_run(RUN)
    assert detail.errors == ()
    assert detail.report == "# Raportti\n<script>alert('test')</script>\n"
    assert detail.proposals == ({"test_title": "Ensimmäinen"}, {"test_title": "Toinen"})
    assert detail.sol_result == {"test_results": [{"test_verdict": "T"}]}
    assert detail.patch.endswith("-old\n+new\n")


def test_absent_and_empty_root_have_distinct_states(tmp_path):
    assert RunReader(tmp_path / "missing").list_runs().state == "not_available"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert RunReader(empty).list_runs().state == "empty"


@pytest.mark.parametrize("run_id", ["../secret", "/etc/passwd", "..", RUN + "/meta.json", RUN + "\n", "20261013-001914-yo-Q6", "２０２６１０１３-001914-yo-q6", "20261013-001914-yo-", "20261013-001914-yo-" + "a" * 33, "20261013-001914-yo-q6\\meta.json", None, 42])
def test_invalid_identifiers_rejected_before_filesystem(publication, run_id, monkeypatch):
    def must_not_open(*args, **kwargs):
        pytest.fail("An invalid run ID reached the filesystem")
    monkeypatch.setattr(runs.os, "open", must_not_open)
    with pytest.raises(ReadFailure, match="Ajotunnuksen") as failure:
        RunReader(publication).read_run(run_id)
    assert failure.value.code == "invalid_run_id"


@pytest.mark.parametrize("root", ["relative/ajot", "/tmp/../ajot", "/tmp/./ajot", "/tmp//ajot", "/", "/tmp/ajot/", "/tmp/ajot\\bad", "/tmp/ajot\0bad"])
def test_unsafe_root_rejected(root):
    with pytest.raises(ValueError):
        RunReader(root)


def test_symlink_in_root_component_rejected(publication, tmp_path):
    linked = tmp_path / "linked"
    linked.symlink_to(publication.parent, target_is_directory=True)
    reader = RunReader(linked / "ajot")
    assert reader.list_runs().state == "error"
    with pytest.raises(ReadFailure) as failure:
        reader.read_run(RUN)
    assert failure.value.code == "unsafe_path"


def test_symlink_run_never_reads_target(publication, tmp_path):
    (publication / OTHER_RUN).symlink_to(publication / RUN, target_is_directory=True)
    result = RunReader(publication).list_runs()
    assert [run.run_id for run in result.runs] == [RUN]
    assert result.errors[0].code == "unsafe_path"
    with pytest.raises(ReadFailure):
        RunReader(publication).read_run(OTHER_RUN)


@pytest.mark.parametrize("filename", list(runs.FILE_LIMITS))
def test_file_symlink_rejected_in_isolation(publication, filename):
    target = publication / RUN / filename
    target.unlink()
    target.symlink_to("/etc/passwd")
    detail = RunReader(publication).read_run(RUN)
    assert any(error.file == filename and error.code == "unsafe_file" for error in detail.errors)
    assert len(detail.errors) == 1


def test_hardlink_rejected(publication):
    target = publication / RUN / "raportti.md"
    os.link(target, publication / "another-name")
    detail = RunReader(publication).read_run(RUN)
    assert detail.report is None
    assert detail.errors[0].code == "unsafe_file"


@pytest.mark.parametrize("kind", ["fifo", "directory"])
def test_special_files_do_not_block_reader(publication, kind):
    target = publication / RUN / "raportti.md"
    target.unlink()
    if kind == "fifo":
        os.mkfifo(target)
    else:
        target.mkdir()
    detail = RunReader(publication).read_run(RUN)
    assert detail.report is None
    assert detail.errors[0].code == "unsafe_file"


def test_device_mode_rejected_before_open(publication, monkeypatch):
    real_stat = runs.os.stat
    real_open = runs.os.open
    def device_stat(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        if path == "raportti.md":
            fields = list(info)
            fields[0] = 0o020600
            return os.stat_result(fields)
        return info
    def guarded_open(path, *args, **kwargs):
        if path == "raportti.md":
            pytest.fail("The reader opened a device")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(runs.os, "stat", device_stat)
    monkeypatch.setattr(runs.os, "open", guarded_open)
    detail = RunReader(publication).read_run(RUN)
    assert detail.errors[0].code == "unsafe_file"


@pytest.mark.parametrize("filename", list(runs.FILE_LIMITS))
def test_file_byte_limits(publication, filename):
    target = publication / RUN / filename
    with target.open("wb") as handle:
        handle.truncate(runs.FILE_LIMITS[filename] + 1)
    detail = RunReader(publication).read_run(RUN)
    assert any(error.file == filename and error.code == "too_large" for error in detail.errors)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"number":NaN}', '{"number":Infinity}', '{"number":1e999}', '{"number":' + "9" * 31 + '}', '[1,2]', 'true', '{"broken":', '{"bad":"\\ud800"}', '{"bad":"\\u0000"}', '{"bad":"\\u202e"}', '{"":1}', '{"a":"' + "x" * (16 * 1024 + 1) + '"}', '{"a":' + "[" * 14 + "0" + "]" * 14 + '}', json.dumps({str(i): i for i in range(65)}), json.dumps({"a": list(range(1025))})])
def test_invalid_json_isolated(publication, text):
    (publication / RUN / "meta.json").write_text(text, encoding="utf-8")
    detail = RunReader(publication).read_run(RUN)
    assert detail.meta is None
    assert detail.report.startswith("# Raportti")
    assert detail.errors[0].code == "invalid_json"
    listed = RunReader(publication).list_runs()
    assert listed.state == "ready"
    assert listed.runs[0].meta is None
    assert listed.runs[0].errors[0].code == "invalid_json"


@pytest.mark.parametrize("content", [b"\xff", b"ok\0bad", b"ok\x1bbad"])
def test_invalid_plain_text_isolated(publication, content):
    (publication / RUN / "raportti.md").write_bytes(content)
    detail = RunReader(publication).read_run(RUN)
    assert detail.report is None
    assert detail.errors[0].code == "invalid_text"


@pytest.mark.parametrize("content,code", [('{}\n\n{}\n', "invalid_jsonl"), ('[]\n', "invalid_json"), ('{}\n{bad}\n', "invalid_json"), ('{"x":"' + "a" * runs.JSONL_LINE_LIMIT + '"}\n', "too_large"), ('{}\n' * (runs.JSONL_RECORD_LIMIT + 1), "too_large")])
def test_invalid_jsonl_has_no_partial_proposals(publication, content, code):
    (publication / RUN / "ehdotukset.jsonl").write_text(content, encoding="utf-8")
    detail = RunReader(publication).read_run(RUN)
    assert detail.proposals == ()
    assert detail.errors[0].code == code


def test_empty_jsonl_and_crlf_are_valid(publication):
    target = publication / RUN / "ehdotukset.jsonl"
    target.write_text("", encoding="utf-8")
    assert RunReader(publication).read_run(RUN).proposals == ()
    target.write_bytes(b'{"a":1}\r\n{"a":2}\r\n')
    assert RunReader(publication).read_run(RUN).proposals == ({"a": 1}, {"a": 2})


def test_missing_optional_files_and_metadata_are_isolated(publication):
    (publication / RUN / "luonnos.patch").unlink()
    (publication / RUN / "meta.json").unlink()
    detail = RunReader(publication).read_run(RUN)
    assert detail.patch is None and detail.meta is None
    assert detail.report
    assert {error.file for error in detail.errors} == {"luonnos.patch", "meta.json"}
    assert all(error.code == "not_found" for error in detail.errors)


def test_wrong_names_are_ignored_and_list_is_bounded(publication):
    (publication / "../not-a-run").mkdir()
    other = publication / OTHER_RUN
    other.mkdir()
    (other / "meta.json").write_text("{}", encoding="utf-8")
    result = RunReader(publication, max_runs=1).list_runs()
    assert [run.run_id for run in result.runs] == [RUN]
    assert result.truncated is True


def test_file_replacement_between_stat_and_open_rejected(publication, monkeypatch):
    real_open = runs.os.open
    replaced = False
    def replacing_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == "raportti.md" and not replaced:
            replaced = True
            original = publication / RUN / "raportti.md"
            original.rename(publication / RUN / "old-report")
            original.write_text("untrusted replacement", encoding="utf-8")
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(runs.os, "open", replacing_open)
    result = RunReader(publication).read_run(RUN)
    assert result.report is None
    assert result.errors[0].code == "changed"


def test_file_changed_during_read_rejected(publication, monkeypatch):
    real_read = runs.os.read
    modified = False
    def modifying_read(fd, count):
        nonlocal modified
        result = real_read(fd, count)
        if result.startswith(b"# Raportti") and not modified:
            modified = True
            (publication / RUN / "raportti.md").write_text("changed content", encoding="utf-8")
        return result
    monkeypatch.setattr(runs.os, "read", modifying_read)
    result = RunReader(publication).read_run(RUN)
    assert result.report is None
    assert result.errors[0].code == "changed"


def test_run_directory_replaced_during_read_rejected(publication, monkeypatch):
    real_read = runs.os.read
    replaced = False
    def replacing_read(fd, count):
        nonlocal replaced
        result = real_read(fd, count)
        if result.startswith(b"# Raportti") and not replaced:
            replaced = True
            (publication / RUN).rename(publication / "old-run")
            (publication / RUN).mkdir()
        return result
    monkeypatch.setattr(runs.os, "read", replacing_read)
    with pytest.raises(ReadFailure) as failure:
        RunReader(publication).read_run(RUN)
    assert failure.value.code == "changed"


def test_root_directory_replaced_during_read_rejected(publication, monkeypatch):
    real_read = runs.os.read
    replaced = False
    def replacing_read(fd, count):
        nonlocal replaced
        result = real_read(fd, count)
        if result.startswith(b"# Raportti") and not replaced:
            replaced = True
            publication.rename(publication.parent / "old-root")
            publication.mkdir()
        return result
    monkeypatch.setattr(runs.os, "read", replacing_read)
    with pytest.raises(ReadFailure) as failure:
        RunReader(publication).read_run(RUN)
    assert failure.value.code == "changed"


def test_deadline_is_reported_without_partial_results(publication, monkeypatch):
    moments = iter([0, 2])
    monkeypatch.setattr(runs.time, "monotonic", lambda: next(moments, 2))
    result = RunReader(publication).list_runs()
    assert result.runs == ()
    assert result.errors[0].code == "timeout"


def test_permission_error_has_no_absolute_path(publication, monkeypatch):
    real_open = runs.os.open
    def forbidden_open(path, flags, *args, **kwargs):
        if path == "raportti.md":
            raise PermissionError(13, "sensitive absolute secret path")
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(runs.os, "open", forbidden_open)
    result = RunReader(publication).read_run(RUN)
    assert result.errors[0].code == "forbidden"
    assert "sensitive" not in result.errors[0].message
    assert str(publication) not in result.errors[0].message


def test_reader_does_not_modify_publication(publication):
    before = {path.relative_to(publication): path.read_bytes() for path in (publication / RUN).iterdir()}
    reader = RunReader(publication)
    reader.list_runs()
    reader.read_run(RUN)
    after = {path.relative_to(publication): path.read_bytes() for path in (publication / RUN).iterdir()}
    assert before == after
