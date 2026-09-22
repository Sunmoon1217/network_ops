"""TTP 解析器测试用例

测试文件从 data/configs/ 目录读取，文件名格式：{vendor}_{type}.txt
使用 Django 自带 TestCase
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

import ingest
from ingest.parsers.factory import ParserFactory

# 模板目录基于 ingest 包定位、数据目录基于项目根：都不依赖测试文件自身位置。
# 原先两者都用 Path(__file__).parent.parent，测试目录一挪动就失效；
# 其中 DATA_DIR 本来就是错的（指向 apps/ingest/data/configs），靠 exists() 静默跳过。
TMPLS_DIR = Path(ingest.__file__).resolve().parent / "parsers" / "tmpls"
DATA_DIR = Path(settings.BASE_DIR) / "data" / "configs"

REGISTERED_PARSERS = ParserFactory.available_parsers()


def _config_file(vendor: str, device_type: str) -> Path:
    return DATA_DIR / f"{vendor.lower()}_{device_type}.txt"


# --- 解析器注册表 ---


class ParserRegistryTest(TestCase):
    """解析器注册表测试"""

    def test_parsers_registered(self):
        self.assertGreater(len(REGISTERED_PARSERS), 0, "没有任何解析器注册")

    def test_all_parsers_instantiation(self):
        for vendor, device_type in REGISTERED_PARSERS:
            with self.subTest(vendor=vendor, device_type=device_type):
                parser = ParserFactory.get_parser_by_keys(vendor, device_type)
                self.assertIsNotNone(parser)
                self.assertTrue(hasattr(parser, "parse"))
                self.assertTrue(parser.template_name, f"{vendor}/{device_type} 未设置 template_name")

    def test_all_templates_exist(self):
        tmpls_dir = TMPLS_DIR
        for vendor, device_type in REGISTERED_PARSERS:
            with self.subTest(vendor=vendor, device_type=device_type):
                parser = ParserFactory.get_parser_by_keys(vendor, device_type)
                found = any((tmpls_dir / subdir / parser.template_name).exists() for subdir in ("configs", "running"))
                self.assertTrue(found, f"模板不存在: {parser.template_name}")

    def test_vendor_aliases(self):
        cases = {"华三": "H3C", "华为": "Huawei", "思科": "Cisco", "山石": "Hillstone", "f5": "F5", "a10": "A10"}
        for alias, expected in cases.items():
            with self.subTest(alias=alias):
                self.assertEqual(ParserFactory._normalize_vendor(alias), expected)

    def test_unknown_parser_raises(self):
        with self.assertRaises(ValueError):
            ParserFactory.get_parser_by_keys("UnknownVendor", "firewall")


# --- 解析器功能 ---


class ParserFunctionalityTest(TestCase):
    """解析器解析功能测试"""

    def test_parse_returns_dict(self):
        for vendor, device_type in REGISTERED_PARSERS:
            config_path = _config_file(vendor, device_type)
            if not config_path.exists():
                continue
            with self.subTest(vendor=vendor, device_type=device_type):
                parser = ParserFactory.get_parser_by_keys(vendor, device_type)
                result = parser.parse(config_path.read_text(encoding="utf-8"))
                self.assertIsInstance(result, dict)

    def test_parse_empty_string(self):
        for vendor, device_type in REGISTERED_PARSERS:
            with self.subTest(vendor=vendor, device_type=device_type):
                parser = ParserFactory.get_parser_by_keys(vendor, device_type)
                result = parser.parse("")
                self.assertIsInstance(result, dict)

    def test_parse_has_results(self):
        for vendor, device_type in REGISTERED_PARSERS:
            config_path = _config_file(vendor, device_type)
            if not config_path.exists():
                continue
            with self.subTest(vendor=vendor, device_type=device_type):
                parser = ParserFactory.get_parser_by_keys(vendor, device_type)
                result = parser.parse(config_path.read_text(encoding="utf-8"))
                self.assertGreater(len(result), 0, f"{vendor}/{device_type} 解析结果为空")


# --- 模板文件 ---


class TemplateTest(TestCase):
    """模板文件完整性测试"""

    def test_configs_dir_exists(self):
        tmpls_dir = TMPLS_DIR
        self.assertTrue((tmpls_dir / "configs").is_dir())

    def test_running_dir_exists(self):
        tmpls_dir = TMPLS_DIR
        self.assertTrue((tmpls_dir / "running").is_dir())

    def test_templates_not_empty(self):
        tmpls_dir = TMPLS_DIR
        for subdir in ("configs", "running"):
            for ttp_file in (tmpls_dir / subdir).glob("*.ttp"):
                with self.subTest(template=ttp_file.name):
                    content = ttp_file.read_text(encoding="utf-8")
                    self.assertGreater(len(content.strip()), 0, f"模板为空: {ttp_file.name}")


class F5PoolMemberSeparatorTest(TestCase):
    """F5 池成员的端口分隔符：名字是 IPv6 字面量时 F5 用点号而不是冒号。

    模板里冒号与点号两条备选行必须都保留，且端口要限成纯数字——不限的话冒号那条
    会把 ``/Common/2001:db8::1.80`` 贪婪切成 name="/Common/2001:db8:"、
    port="1.80"，回退行永远轮不到，表现为「端口被下一条成员覆盖」。
    """

    def _members(self, member_lines: str) -> list:
        config = f"ltm pool /Common/pool_x {{\n    members {{\n{member_lines}    }}\n}}\n"
        parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(config)
        members = parsed["pools"]["members"]
        return members if isinstance(members, list) else [members]

    def test_colon_and_dot_separator_both_parse(self):
        members = self._members(
            "        /Common/node_a:80 {\n            address 10.0.0.1\n        }\n"
            "        /Common/2001:db8::1.8080 {\n            address 2001:db8::1\n        }\n"
        )
        assert [(m["name"], m["port"]) for m in members] == [
            ("/Common/node_a", "80"),
            ("/Common/2001:db8::1", "8080"),
        ]

    def test_ipv6_literal_not_split_at_first_colon(self):
        members = self._members("        /Common/2001:db8::1.80 {\n            address 2001:db8::1\n        }\n")
        assert members[0]["name"] == "/Common/2001:db8::1"  # 不是 "/Common/2001:db8:"
        assert members[0]["port"] == "80"  # 不是 "1.80"

    def test_ipv6_member_does_not_steal_neighbour_port(self):
        """混排时每条成员各拿自己的端口，v6 的不能被后面 v4 的覆盖"""
        members = self._members(
            "        /Common/2001:db8::1.80 {\n            address 2001:db8::1\n        }\n"
            "        /Common/node_v4:8080 {\n            address 10.0.0.1\n        }\n"
            "        /Common/2001:db8::2.443 {\n            address 2001:db8::2\n        }\n"
        )
        assert [(m["name"], m["port"]) for m in members] == [
            ("/Common/2001:db8::1", "80"),
            ("/Common/node_v4", "8080"),
            ("/Common/2001:db8::2", "443"),
        ]
