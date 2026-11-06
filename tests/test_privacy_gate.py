"""门禁得真能拦：手机号、QQ 号、昵称；同时别把色值和文件模式当成隐私。

测试里的数字用拼接写，免得这个文件自己先被门禁拦下来。
"""
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PHONE = "138" + "1234" + "5678"      # 形状对，但不是真号
QQ = "123" + "456" + "789"          # 9 位


def gate():
    mod = importlib.import_module("privacy_gate")
    return importlib.reload(mod)


class TestRules(unittest.TestCase):
    def setUp(self):
        self.gate = gate()

    def hits(self, line: str) -> list[str]:
        found = []
        for name, rx, _why in self.gate.RULES:
            m = rx.search(line)
            if not m:
                continue
            check = self.gate.NUMBER_CHECK.get(name)
            if check and not check(m, line):
                continue
            found.append(name)
        return found

    def test_mobile(self):
        self.assertIn("mobile", self.hits(f'  target: "{PHONE}"'))

    def test_qq_number(self):
        self.assertIn("qq", self.hits(f"  qq: {QQ}"))
        self.assertIn("qq", self.hits(f"uin={QQ},"))

    def test_hex_color_is_not_qq(self):
        for line in ("--bg:#121115;", "border-color:#20161a;", ".btn{color:#313943}"):
            self.assertNotIn("qq", self.hits(line))

    def test_file_mode_is_not_qq(self):
        self.assertNotIn("qq", self.hits('{"mode": "100644", "type": "blob"}'))
        self.assertNotIn("qq", self.hits('"chcp 65001 >nul"'))

    def test_local_word_rule(self):
        """本地词表里的词，必须能被自己那条规则匹配到（不把词写进测试）。"""
        rules = [r for r in self.gate.RULES if r[0] == "私人词"]
        path = self.gate.LOCAL_WORDS
        if not rules or not path.exists():
            self.skipTest("本机没有 config/privacy.local.txt")
        words = [ln.strip().split("|")[0] for ln in
                 path.read_text(encoding="utf-8-sig").splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(words, "词表是空的")
        self.assertTrue(any(rx.search(words[0]) for _n, rx, _w in rules))


class TestScanRepo(unittest.TestCase):
    """拿仓库自己的 HEAD 跑一遍：一个都不该命中。"""

    def test_head_is_clean(self):
        mod = gate()
        hits = [h for h in mod.scan(mod.tracked_files(), mod.read_head) if h[4] != "已放行"]
        self.assertEqual(hits, [], f"仓库里有隐私字符：{hits[:3]}")


if __name__ == "__main__":
    unittest.main()