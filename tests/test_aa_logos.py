# -*- coding: utf-8 -*-
"""aa_logos 模块单测：slug 解析 / 后缀回退 / 缓存 / 负缓存 / SVG 尺寸注入。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import aa_logos  # noqa: E402


class FakeResp:
    def __init__(self, status=200, body=b'fake'):
        self.status = status
        self._body = body

    def read(self, n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestSlugify(unittest.TestCase):
    def test_alias_priority(self):
        self.assertEqual(aa_logos.slugify_creator('Amazon'), 'aws')
        self.assertEqual(aa_logos.slugify_creator('AI21 Labs'), 'ai21')
        self.assertEqual(aa_logos.slugify_creator('LG AI Research'), 'lg')

    def test_regular_rule(self):
        self.assertEqual(aa_logos.slugify_creator('DeepSeek'), 'deepseek')
        self.assertEqual(aa_logos.slugify_creator('Z AI'), 'zai')
        self.assertEqual(aa_logos.slugify_creator('Trillion Labs'), 'trillionlabs')

    def test_empty(self):
        self.assertEqual(aa_logos.slugify_creator(''), '')
        self.assertEqual(aa_logos.slugify_creator(None), '')


class TestSvgSize(unittest.TestCase):
    def test_inject_when_missing(self):
        data = b'<svg viewBox="0 0 24 24"><path/></svg>'
        out = aa_logos._inject_svg_size(data)
        self.assertIn(b'width="96"', out)
        self.assertIn(b'height="96"', out)

    def test_keep_when_present(self):
        data = b'<svg width="10" height="10"><path/></svg>'
        self.assertEqual(aa_logos._inject_svg_size(data), data)


class TestGetLogo(unittest.TestCase):
    def setUp(self):
        # 每个用例用独立临时缓存目录，互不污染
        self.tmp = Path(self.enterContext(__import__('tempfile').TemporaryDirectory()))
        self.patcher = mock.patch.object(aa_logos, '_CACHE_DIR', self.tmp)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        aa_logos._missing_cache.clear()

    def test_fetch_first_ext_then_cache(self):
        with mock.patch.object(aa_logos, '_fetch_remote',
                               side_effect=[b'<svg/>', None, None]) as mf:
            got = aa_logos.get_logo('DeepSeek')
        self.assertIsNotNone(got)
        body, ctype = got
        self.assertEqual(ctype, 'image/svg+xml')
        self.assertEqual(mf.call_args_list[0].args, ('deepseek', 'svg'))
        # 缓存文件已写入
        self.assertTrue((self.tmp / 'deepseek.svg').is_file())
        # 第二次直接命中磁盘，不再发网络
        with mock.patch.object(aa_logos, '_fetch_remote') as mf2:
            got2 = aa_logos.get_logo('DeepSeek')
        self.assertEqual(got2[1], 'image/svg+xml')
        mf2.assert_not_called()

    def test_ext_fallback_to_png(self):
        with mock.patch.object(aa_logos, '_fetch_remote',
                               side_effect=[None, b'pngbytes', None]):
            got = aa_logos.get_logo('Mistral')
        self.assertIsNotNone(got)
        self.assertEqual(got[1], 'image/png')

    def test_negative_cache(self):
        with mock.patch.object(aa_logos, '_fetch_remote', return_value=None):
            self.assertIsNone(aa_logos.get_logo('China Mobile'))
        # 负缓存后不再发网络
        with mock.patch.object(aa_logos, '_fetch_remote') as mf:
            self.assertIsNone(aa_logos.get_logo('China Mobile'))
            mf.assert_not_called()
        # 磁盘 marker 已写
        self.assertTrue((self.tmp / 'chinamobile.missing').is_file())

    def test_invalid_slug_rejected(self):
        self.assertIsNone(aa_logos.get_logo(''))
        self.assertIsNone(aa_logos.get_logo('X' * 100))

    def test_concurrent_double_fetch_dedup(self):
        """加锁双检：第二个线程等待锁后直接命中磁盘，不再重复拉取。"""
        calls = []

        def fake_fetch(slug, ext):
            calls.append((slug, ext))
            return b'<svg/>'

        with mock.patch.object(aa_logos, '_fetch_remote', side_effect=fake_fetch):
            t1_res = aa_logos.get_logo('OpenAI')
            t2_res = aa_logos.get_logo('OpenAI')   # 串行模拟：此时磁盘已有缓存
        self.assertIsNotNone(t1_res)
        self.assertIsNotNone(t2_res)
        self.assertEqual(len(calls), 1)


class TestWarmup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(__import__('tempfile').TemporaryDirectory()))
        self.patcher = mock.patch.object(aa_logos, '_CACHE_DIR', self.tmp)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        aa_logos._missing_cache.clear()
        # 每个用例独立锁状态
        self.lock_patcher = mock.patch.object(aa_logos, '_warmup_lock',
                                              __import__('threading').Lock())
        self.lock_patcher.start()
        self.addCleanup(self.lock_patcher.stop)

    def _models(self, names):
        return [{'model_creator': {'name': n}} for n in names]

    def test_warmup_dedupes_creators(self):
        calls = []

        def fake_fetch(slug, ext):
            calls.append(slug)
            return b'<svg/>'

        with mock.patch.object(aa_logos, '_fetch_remote', side_effect=fake_fetch), \
             mock.patch.object(aa_logos.time, 'sleep'):
            res = aa_logos.warmup_logos(self._models(['OpenAI', 'DeepSeek', 'OpenAI', 'DeepSeek']))
        self.assertEqual(res['total'], 2)
        self.assertEqual(res['hit'], 2)
        self.assertEqual(res['miss'], 0)
        self.assertEqual(sorted(set(calls)), ['deepseek', 'openai'])
        # 磁盘已落盘
        self.assertTrue((self.tmp / 'openai.svg').is_file())
        self.assertTrue((self.tmp / 'deepseek.svg').is_file())

    def test_warmup_skips_when_running(self):
        # 模拟已有预热在跑：先占住锁
        aa_logos._warmup_lock.acquire()
        try:
            with mock.patch.object(aa_logos, '_fetch_remote') as mf:
                res = aa_logos.warmup_logos(self._models(['OpenAI']))
            self.assertTrue(res['skipped'])
            mf.assert_not_called()
        finally:
            aa_logos._warmup_lock.release()

    def test_warmup_counts_missing_logo(self):
        with mock.patch.object(aa_logos, '_fetch_remote', return_value=None), \
             mock.patch.object(aa_logos.time, 'sleep'):
            res = aa_logos.warmup_logos(self._models(['China Mobile']))
        self.assertEqual(res['total'], 1)
        self.assertEqual(res['hit'], 0)
        self.assertEqual(res['miss'], 1)
        self.assertFalse(res['skipped'])

    def test_warmup_empty_models(self):
        res = aa_logos.warmup_logos([])
        self.assertEqual(res['total'], 0)
        res2 = aa_logos.warmup_logos(None)
        self.assertEqual(res2['total'], 0)

    def test_warmup_second_run_disk_hit_no_fetch(self):
        with mock.patch.object(aa_logos, '_fetch_remote', return_value=b'<svg/>'), \
             mock.patch.object(aa_logos.time, 'sleep'):
            aa_logos.warmup_logos(self._models(['OpenAI']))
        # 第二轮：全部命中磁盘，零网络请求
        with mock.patch.object(aa_logos, '_fetch_remote') as mf2, \
             mock.patch.object(aa_logos.time, 'sleep'):
            res = aa_logos.warmup_logos(self._models(['OpenAI']))
        mf2.assert_not_called()
        self.assertEqual(res['hit'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
