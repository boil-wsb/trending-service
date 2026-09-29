# -*- coding: utf-8 -*-
"""指数分时数据层单测：腾讯/新浪/申万分时解析 + fetch_minute_lines 分派 + 周/月K聚合。

分时数据结构依据 2026-09-28 实测（debug_out/probe_minute_sources*.txt，已清理）：
- 腾讯 data.data = ["0930 3878.41 3901496 6172666205.40", ...]（HHMM 价格 累计量 累计额）
- 新浪 5 分钟 K 返回近几个交易日，需截取最新一天
- 申万 index_min_sw 列：代码/名称/价格/日期/时间（10 秒粒度，仅价格）
"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetchers.index import IndexFetcher  # noqa: E402


class FakeMinuteResp:
    """urllib urlopen 上下文管理器替身"""

    def __init__(self, payload):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload)
        else:
            body = payload
        self._body = body.encode('utf-8') if isinstance(body, str) else body

    def read(self, n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


TX_PAYLOAD = {
    'code': 0,
    'data': {
        'sh000001': {
            'data': {
                'date': '20260928',
                'data': [
                    '0930 3878.41 3901496 6172666205.40',
                    '0931 3869.86 20844108 35445662366.20',
                    '0932 3870.39 30259315 51407811065.50',
                ]
            }
        }
    }
}


class TestFetchMinuteTx(unittest.TestCase):
    """腾讯 1 分钟分时解析（市场指数主源）"""

    def _run(self, payload):
        f = IndexFetcher()
        with mock.patch('urllib.request.urlopen', return_value=FakeMinuteResp(payload)):
            return f._fetch_minute_tx('000001')

    def test_parse_basic(self):
        d = self._run(TX_PAYLOAD)
        self.assertEqual(d['times'], ['09:30', '09:31', '09:32'])
        self.assertEqual(d['price'], [3878.41, 3869.86, 3870.39])
        self.assertEqual(d['interval_seconds'], 60)
        self.assertEqual(d['date'], '2026-09-28')
        self.assertIsNone(d['prev_close'])  # 由 server 层从 DB 日线补

    def test_volume_cum_diff(self):
        """累计量差分为每分钟成交量"""
        d = self._run(TX_PAYLOAD)
        self.assertEqual(d['volume'], [3901496.0, 16942612.0, 9415207.0])

    def test_avg_price_cum_mean(self):
        """均价线 = 分钟价累计平均（指数量额比值不可用，见 fetch_minute_lines docstring）"""
        d = self._run(TX_PAYLOAD)
        self.assertAlmostEqual(d['avg_price'][0], 3878.41, places=2)
        self.assertAlmostEqual(d['avg_price'][1], (3878.41 + 3869.86) / 2, places=2)

    def test_bad_rows_skipped(self):
        """异常行（字段不足/价格为 0）跳过且不影响其余点"""
        payload = json.loads(json.dumps(TX_PAYLOAD))
        payload['data']['sh000001']['data']['data'] = [
            '0930 3878.41 3901496 6172666205.40',
            'badrow',
            '0931 0 0 0',
            '0932 3870.39 30259315 51407811065.50',
        ]
        d = self._run(payload)
        self.assertEqual(d['times'], ['09:30', '09:32'])

    def test_empty_rows_return_none(self):
        payload = json.loads(json.dumps(TX_PAYLOAD))
        payload['data']['sh000001']['data']['data'] = []
        self.assertIsNone(self._run(payload))


SINA_PAYLOAD = [
    {'day': '2026-09-25 15:00:00', 'close': '3888.37', 'volume': '999'},
    {'day': '2026-09-28 09:35:00', 'close': '3878.41', 'volume': '100'},
    {'day': '2026-09-28 09:40:00', 'close': '3869.86', 'volume': '200'},
]


class TestFetchMinuteSina(unittest.TestCase):
    """新浪 5 分钟 K 截当日（市场指数备源）"""

    def _run(self, payload):
        f = IndexFetcher()
        with mock.patch('urllib.request.urlopen', return_value=FakeMinuteResp(payload)):
            return f._fetch_minute_sina('000001')

    def test_latest_day_only(self):
        d = self._run(SINA_PAYLOAD)
        self.assertEqual(d['date'], '2026-09-28')
        self.assertEqual(d['times'], ['09:35', '09:40'])
        self.assertEqual(d['price'], [3878.41, 3869.86])
        self.assertEqual(d['interval_seconds'], 300)

    def test_empty_return_none(self):
        self.assertIsNone(self._run([]))


class TestFetchMinuteSw(unittest.TestCase):
    """申万 10 秒分时解析（仅价格，无量额）"""

    def test_parse(self):
        import pandas as pd
        df = pd.DataFrame({
            '代码': ['801030'] * 3,
            '名称': ['基础化工'] * 3,
            '价格': [4228.66, 4219.48, 4209.45],
            '日期': [date(2026, 9, 28)] * 3,
            '时间': ['09:30:00', '09:30:10', '09:30:20'],
        })
        ak = mock.MagicMock()
        ak.index_min_sw = mock.MagicMock(return_value=df)
        f = IndexFetcher()
        with mock.patch.dict('sys.modules', {'akshare': ak}):
            d = f._fetch_minute_sw('801030')
        self.assertEqual(d['times'], ['09:30:00', '09:30:10', '09:30:20'])
        self.assertEqual(d['price'], [4228.66, 4219.48, 4209.45])
        self.assertEqual(d['interval_seconds'], 10)
        self.assertEqual(d['date'], '2026-09-28')
        self.assertIsNone(d['avg_price'])
        self.assertIsNone(d['volume'])


class TestFetchMinuteDispatch(unittest.TestCase):
    """fetch_minute_lines 分派：概念不支持 / 主备源回退 / 全失败报错"""

    def test_concept_not_supported(self):
        f = IndexFetcher()
        d = f.fetch_minute_lines('共封装光学(CPO)')
        self.assertFalse(d['supported'])
        self.assertEqual(d['price'], [])

    def test_market_fallback_to_sina(self):
        f = IndexFetcher()
        sina_data = {'times': ['09:35'], 'price': [1.0], 'avg_price': [1.0],
                     'volume': [1], 'interval_seconds': 300,
                     'date': '2026-09-28', 'prev_close': None}
        with mock.patch.object(f, '_fetch_minute_tx', side_effect=RuntimeError('tx down')), \
             mock.patch.object(f, '_fetch_minute_sina', return_value=dict(sina_data)):
            d = f.fetch_minute_lines('000001')
        self.assertTrue(d['supported'])
        self.assertEqual(d['interval_seconds'], 300)

    def test_market_all_fail_raises(self):
        f = IndexFetcher()
        with mock.patch.object(f, '_fetch_minute_tx', side_effect=RuntimeError('tx down')), \
             mock.patch.object(f, '_fetch_minute_sina', side_effect=RuntimeError('sina down')):
            with self.assertRaises(RuntimeError):
                f.fetch_minute_lines('000001')


class TestAggregateKline(unittest.TestCase):
    """周/月K聚合（既有能力，补单测防回归）"""

    def setUp(self):
        # 2026-09-21(周一) ~ 09-28(周一)，覆盖跨周/同月
        self.daily = [
            {'date': '2026-09-21', 'open': 100, 'close': 101, 'high': 102, 'low': 99, 'volume': 10, 'amount': 1},
            {'date': '2026-09-22', 'open': 101, 'close': 103, 'high': 104, 'low': 100, 'volume': 20, 'amount': 2},
            {'date': '2026-09-25', 'open': 103, 'close': 105, 'high': 106, 'low': 102, 'volume': 30, 'amount': 3},
            {'date': '2026-09-28', 'open': 105, 'close': 104, 'high': 107, 'low': 103, 'volume': 40, 'amount': 4},
        ]

    def test_week_aggregate(self):
        out = IndexFetcher.aggregate_kline(self.daily, 'week')
        self.assertEqual(len(out), 2)
        w1 = out[0]
        self.assertEqual(w1['date'], '2026-09-25')   # 组内最后交易日
        self.assertEqual(w1['open'], 100)
        self.assertEqual(w1['close'], 105)
        self.assertEqual(w1['high'], 106)
        self.assertEqual(w1['low'], 99)
        self.assertEqual(w1['volume'], 60)
        self.assertEqual(w1['change_pct'], 0.0)      # 首组无昨收
        w2 = out[1]
        self.assertEqual(w2['date'], '2026-09-28')
        self.assertEqual(w2['open'], 105)
        self.assertEqual(w2['close'], 104)
        self.assertAlmostEqual(w2['change_pct'], round((104 - 105) / 105 * 100, 4), places=4)

    def test_month_aggregate(self):
        out = IndexFetcher.aggregate_kline(self.daily, 'month')
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m['date'], '2026-09-28')
        self.assertEqual(m['open'], 100)
        self.assertEqual(m['close'], 104)
        self.assertEqual(m['high'], 107)
        self.assertEqual(m['low'], 99)
        self.assertEqual(m['volume'], 100)

    def test_invalid_period_passthrough(self):
        self.assertEqual(IndexFetcher.aggregate_kline(self.daily, 'day'), self.daily)


if __name__ == '__main__':
    unittest.main(verbosity=2)
