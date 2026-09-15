"""TTP 解析器测试用例

测试文件从 data/configs/ 目录读取，文件名格式：{vendor}_{type}.txt
使用 Django 自带 TestCase
"""

from pathlib import Path

from django.test import TestCase

from ops.parsers.factory import ParserFactory

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "configs"

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
        tmpls_dir = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"
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
        tmpls_dir = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"
        self.assertTrue((tmpls_dir / "configs").is_dir())

    def test_running_dir_exists(self):
        tmpls_dir = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"
        self.assertTrue((tmpls_dir / "running").is_dir())

    def test_templates_not_empty(self):
        tmpls_dir = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"
        for subdir in ("configs", "running"):
            for ttp_file in (tmpls_dir / subdir).glob("*.ttp"):
                with self.subTest(template=ttp_file.name):
                    content = ttp_file.read_text(encoding="utf-8")
                    self.assertGreater(len(content.strip()), 0, f"模板为空: {ttp_file.name}")
