#!/usr/bin/env python3
"""
知乎Cookie自动修复工具
当检测到401错误时，自动执行Cookie更新流程
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright


def check_recent_401_error():
    """检查最近是否有401错误"""
    log_file = Path(__file__).parent.parent / 'data' / 'logs' / 'trending_service.log'
    
    if not log_file.exists():
        return False, "日志文件不存在"
    
    # 读取最近100行日志
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-100:]
    except Exception as e:
        return False, f"读取日志失败: {e}"
    
    # 检查是否有401错误
    for line in lines:
        if '401 Client Error' in line and '知乎' in line:
            # 提取时间
            time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                error_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                # 如果是最近1小时的错误
                if datetime.now() - error_time < timedelta(hours=1):
                    return True, f"发现最近的401错误: {line.strip()}"
    
    return False, "未发现最近的401错误"


def get_zhihu_cookie_auto():
    """自动获取知乎Cookie（无需用户按回车）"""
    print("=" * 60)
    print("知乎 Cookie 自动更新工具")
    print("=" * 60)
    print("\n检测到知乎授权失效，需要更新Cookie...")
    print("浏览器将自动打开，请完成以下步骤：")
    print("1. 在浏览器中登录知乎账号")
    print("2. 登录成功后，脚本会自动保存Cookie")
    print("=" * 60)
    print()

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

        # 等待用户登录（通过检测URL变化或特定元素）
        print("\n⏳ 请在浏览器中登录知乎...")
        print("登录成功后，脚本会自动检测并保存Cookie")
        
        # 等待登录成功（最多等待5分钟）
        login_success = False
        for i in range(300):  # 300秒 = 5分钟
            try:
                # 检查是否已登录（通过查找用户头像或用户名元素）
                user_element = page.query_selector('.AppHeader-profileEntry, .ProfileCard, [data-za-detail-view-path-module="UserProfile"]')
                if user_element:
                    login_success = True
                    print("\n✅ 检测到登录成功！")
                    break
            except:
                pass
            
            # 每秒检查一次
            import time
            time.sleep(1)
            
            # 显示进度
            if i % 30 == 0 and i > 0:
                print(f"  已等待 {i} 秒，请完成登录...")
        
        if not login_success:
            print("\n⚠️ 等待超时，请手动按回车键保存当前Cookie...")
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
    print("Cookie 更新完成!")
    print("=" * 60)
    return True


def test_zhihu_fetch():
    """测试知乎热榜获取"""
    print("\n🧪 正在测试知乎热榜获取...")
    
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.fetchers import ZhihuHotFetcher
    from src.utils import get_logger
    
    logger = get_logger('test_zhihu')
    fetcher = ZhihuHotFetcher(logger=logger)
    items = fetcher.fetch()
    
    if items:
        print(f"✅ 测试成功！获取到 {len(items)} 条知乎热榜数据")
        print("\n前5条数据:")
        for i, item in enumerate(items[:5], 1):
            print(f"  {i}. {item.title[:40]}... (热度: {item.hot_score:,.0f})")
        return True
    else:
        print("❌ 测试失败！未能获取到知乎热榜数据")
        return False


def main():
    """主函数"""
    print("🔍 检查知乎Cookie状态...")
    
    # 检查是否有401错误
    has_error, message = check_recent_401_error()
    
    if has_error:
        print(f"⚠️ {message}")
        print("\n🔄 开始自动修复流程...")
        
        # 获取新Cookie
        if get_zhihu_cookie_auto():
            # 测试获取
            test_zhihu_fetch()
        else:
            print("❌ Cookie更新失败")
    else:
        print(f"✅ {message}")
        print("\n🧪 直接测试知乎热榜获取...")
        test_zhihu_fetch()


if __name__ == "__main__":
    main()
