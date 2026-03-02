#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知乎 Cookie 获取工具
使用 Playwright 打开浏览器，让用户手动登录后自动保存 Cookie
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright


def get_zhihu_cookie():
    """获取知乎 Cookie"""
    print("=" * 60)
    print("知乎 Cookie 获取工具")
    print("=" * 60)
    print("\n步骤:")
    print("1. 浏览器将自动打开知乎登录页面")
    print("2. 请手动登录知乎账号")
    print("3. 登录成功后，按回车键保存 Cookie")
    print("4. Cookie 将保存到 data/zhihu_cookies.json")
    print("\n注意: 登录后请不要关闭浏览器，按回车键即可保存")
    print("=" * 60)
    print()

    input("按回车键开始...")

    cookies_file = Path(__file__).parent.parent / 'data' / 'zhihu_cookies.json'

    with sync_playwright() as p:
        # 启动浏览器（非无头模式，方便用户操作）
        browser = p.chromium.launch(headless=False)

        # 创建上下文
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )

        # 创建页面
        page = context.new_page()

        # 访问知乎
        print("🌐 正在打开知乎...")
        page.goto('https://www.zhihu.com', wait_until='networkidle')

        # 等待用户登录
        print("\n⏳ 请在浏览器中登录知乎...")
        print("登录成功后，请按回车键保存 Cookie")
        input()

        # 获取 Cookie
        cookies = context.cookies()

        # 保存 Cookie
        cookies_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Cookie 已保存到: {cookies_file}")
        print(f"📊 共 {len(cookies)} 个 Cookie")

        # 显示关键 Cookie
        important_cookies = ['z_c0', 'q_c1', 'tgw_l7_route', '_xsrf']
        print("\n关键 Cookie:")
        for cookie in cookies:
            if cookie['name'] in important_cookies:
                print(f"  - {cookie['name']}: {cookie['value'][:30]}...")

        # 关闭浏览器
        browser.close()

    print("\n" + "=" * 60)
    print("Cookie 获取完成!")
    print("现在可以使用 python -m src.main --refresh zhihu 获取热榜数据")
    print("=" * 60)


if __name__ == "__main__":
    get_zhihu_cookie()
