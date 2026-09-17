"""`import_server_owners` 管理命令测试。

数据源是 xlsx（sheet 名 servers，列 hostname / ip / owner）。这里在 tmp_path 里
现造工作簿，覆盖：按列名取（表头换序 / 多列）、ip 唯一键更新、文件内重复、
非法行报错退出、缺列与缺 sheet 的提示、--dry-run 不写库。
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from assets.models import ServerOwner

SHEET = "servers"


def _write_xlsx(path, rows, header=("hostname", "ip", "owner"), sheet=SHEET):
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.append(list(header))
    for row in rows:
        worksheet.append(list(row))
    workbook.save(path)
    return path


def _run(path, *args) -> str:
    from io import StringIO

    out = StringIO()
    call_command("import_server_owners", "--file", str(path), *args, stdout=out, stderr=StringIO())
    return out.getvalue()


@pytest.mark.django_db
def test_import_creates_and_updates(tmp_path):
    path = _write_xlsx(
        tmp_path / "servers.xlsx",
        [
            ("srv-01", "10.0.0.1", "张三"),
            ("srv-02", "10.0.0.2", "李四"),
        ],
    )

    output = _run(path)

    assert "新建 2 条" in output
    assert ServerOwner.objects.get(ip="10.0.0.1").owner == "张三"
    assert set(ServerOwner.objects.values_list("hostname", flat=True)) == {"srv-01", "srv-02"}

    # 同一个 ip 再导一次：改成更新，不新增
    path = _write_xlsx(tmp_path / "servers2.xlsx", [("srv-01-new", "10.0.0.1", "王五")])
    output = _run(path)

    assert "新建 0 条" in output
    assert "更新 1 条" in output
    updated = ServerOwner.objects.get(ip="10.0.0.1")
    assert (updated.hostname, updated.owner) == ("srv-01-new", "王五")
    assert ServerOwner.objects.count() == 2


@pytest.mark.django_db
def test_columns_are_matched_by_name_not_position(tmp_path):
    """表头换序、夹带无关列都不该串位"""
    path = _write_xlsx(
        tmp_path / "reordered.xlsx",
        [("10.0.0.9", "备注", "srv-09", "赵六")],
        header=("ip", "remark", "hostname", "owner"),
    )

    _run(path)

    item = ServerOwner.objects.get()
    assert (item.ip, item.hostname, item.owner) == ("10.0.0.9", "srv-09", "赵六")


@pytest.mark.django_db
def test_ipv6_is_normalized(tmp_path):
    """大小写 / 展开写法要落在同一条记录上"""
    path = _write_xlsx(tmp_path / "v6.xlsx", [("srv-v6", "2001:DB8:0:0::1", "张三")])

    _run(path)

    assert ServerOwner.objects.get().ip == "2001:db8::1"


@pytest.mark.django_db
def test_duplicate_ip_in_file_keeps_last(tmp_path):
    path = _write_xlsx(
        tmp_path / "dup.xlsx",
        [
            ("srv-a", "10.0.0.1", "先"),
            ("srv-b", "10.0.0.1", "后"),
        ],
    )

    output = _run(path)

    assert "重复" in output
    assert ServerOwner.objects.count() == 1
    assert ServerOwner.objects.get(ip="10.0.0.1").owner == "后"


@pytest.mark.django_db
def test_status_is_not_overwritten(tmp_path):
    """这份表没有 status 列，更新时不能把手工停用的记录导成启用"""
    ServerOwner.objects.create(ip="10.0.0.1", hostname="old", owner="old", status="disabled")
    path = _write_xlsx(tmp_path / "keep-status.xlsx", [("srv-01", "10.0.0.1", "张三")])

    _run(path)

    item = ServerOwner.objects.get(ip="10.0.0.1")
    assert item.owner == "张三"
    assert item.status == "disabled"


@pytest.mark.django_db
def test_invalid_rows_raise_and_write_nothing(tmp_path):
    """非法 ip 行要以非零退出码收尾，且整批不落库（事务回滚）"""
    path = _write_xlsx(
        tmp_path / "bad.xlsx",
        [
            ("srv-01", "10.0.0.1", "张三"),
            ("srv-02", "10.0.0.999", "李四"),
            ("srv-03", "", "王五"),
        ],
    )

    with pytest.raises(CommandError, match="2 行数据有问题，整批未导入"):
        _run(path)

    assert ServerOwner.objects.count() == 0


@pytest.mark.django_db
def test_blank_rows_are_skipped(tmp_path):
    path = _write_xlsx(tmp_path / "blank.xlsx", [("srv-01", "10.0.0.1", "张三"), (None, None, None)])

    output = _run(path)

    assert "新建 1 条" in output
    assert ServerOwner.objects.count() == 1


@pytest.mark.django_db
def test_missing_column_lists_actual_header(tmp_path):
    path = _write_xlsx(tmp_path / "nocol.xlsx", [("srv-01", "10.0.0.1")], header=("hostname", "ip"))

    with pytest.raises(CommandError, match="缺少列: owner"):
        _run(path)


@pytest.mark.django_db
def test_missing_sheet_lists_available(tmp_path):
    path = _write_xlsx(tmp_path / "other.xlsx", [("srv-01", "10.0.0.1", "张三")], sheet="别的表")

    with pytest.raises(CommandError, match="工作表 'servers' 不存在"):
        _run(path)


@pytest.mark.django_db
def test_missing_file(tmp_path):
    with pytest.raises(CommandError, match="文件不存在"):
        _run(tmp_path / "nope.xlsx")


@pytest.mark.django_db
def test_dry_run_does_not_write(tmp_path):
    path = _write_xlsx(tmp_path / "dry.xlsx", [("srv-01", "10.0.0.1", "张三")])

    output = _run(path, "--dry-run")

    assert "--dry-run：没有写库" in output
    assert "将新建 1 条" in output
    assert ServerOwner.objects.count() == 0
