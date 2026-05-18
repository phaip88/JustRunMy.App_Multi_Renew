#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import random
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
PANEL_URL = "https://justrunmy.app/panel"

EMAIL = os.environ.get("ACC")
PASSWORD = os.environ.get("ACC_PWD")
TG_BOT_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_ID")
RUN_ATTEMPT = os.environ.get("RUN_ATTEMPT", "").strip()
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
CAMOUFOX_PATH = os.environ.get("CAMOUFOX_PATH", "./camoufox/camoufox")

if not EMAIL or not PASSWORD:
    print("致命错误：未找到 ACC 或 ACC_PWD 环境变量！")
    sys.exit(1)

DYNAMIC_APP_NAME = "未知应用"


def attempt_suffix():
    return f"（第 {RUN_ATTEMPT} 次执行）" if RUN_ATTEMPT else ""


def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG_TOKEN 或 TG_ID，跳过 Telegram 推送。")
        return

    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))
    text = (
        f"{DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}{attempt_suffix()}\n"
        f"剩余: {time_left}\n"
        f"时间: {current_time}"
    )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=10,
        )
        print("  Telegram 通知发送成功！" if response.status_code == 200 else f"  Telegram 通知发送失败: {response.text}")
    except Exception as exc:
        print(f"  Telegram 通知发送异常: {exc}")


def send_tg_photo(image_path, caption):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG_TOKEN 或 TG_ID，跳过 Telegram 截图推送。")
        return
    if not os.path.exists(image_path):
        print(f"截图不存在，跳过 Telegram 推送: {image_path}")
        return

    try:
        with open(image_path, "rb") as image_file:
            response = requests.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT_ID, "caption": f"{caption}{attempt_suffix()}"},
                files={"photo": image_file},
                timeout=20,
            )
        print("  Telegram 截图发送成功！" if response.status_code == 200 else f"  Telegram 截图发送失败: {response.text}")
    except Exception as exc:
        print(f"  Telegram 截图发送异常: {exc}")


def save_failure_screenshot(page, image_path, status_text, time_left="未知"):
    page.screenshot(path=image_path, full_page=True)
    send_tg_message("[X]", status_text, time_left)
    send_tg_photo(image_path, status_text)


def human_mouse_move(page, x, y, steps=15):
    for _ in range(steps):
        page.mouse.move(
            x + random.randint(-5, 5),
            y + random.randint(-5, 5),
        )
        time.sleep(random.randint(20, 50) / 1000)


def human_type(locator, text):
    locator.fill("")
    for char in text:
        locator.type(char, delay=random.randint(50, 150))


def turnstile_state(page):
    return page.evaluate(
        """
        () => {
            const token = document.querySelector('input[name="cf-turnstile-response"]');
            const bodyText = (document.body?.innerText || '').toLowerCase();
            return {
                tokenReady: !!(token && token.value && token.value.length > 20),
                verifying: bodyText.includes('verifying'),
                failed: bodyText.includes('verification failed'),
            };
        }
        """
    )


def wait_for_turnstile_token(page, seconds, label):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = turnstile_state(page)
        if state["tokenReady"]:
            print(f"  {label} 已通过")
            return True
        if state["failed"]:
            print(f"  {label} 已明确失败")
            return False
        if state["verifying"]:
            print(f"  {label} 仍在自动验证中...")
        time.sleep(1)
    return False


def find_turnstile_box(page):
    selectors = [
        'iframe[src*="turnstile"]',
        'iframe[src*="challenges.cloudflare.com"]',
        '[data-sitekey]',
        '.cf-turnstile',
        '[class*="turnstile"]',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count():
            box = locator.bounding_box()
            if box:
                print(f"  找到 Turnstile: {selector}")
                return box
    return None


def click_turnstile_like_human(page):
    box = find_turnstile_box(page)
    if not box:
        print("  未找到可点击的 Turnstile 区域")
        return False

    click_x = box["x"] + min(24, box["width"] * 0.12)
    click_y = box["y"] + box["height"] / 2
    print(f"  移动鼠标到 Turnstile checkbox ({click_x:.0f}, {click_y:.0f})")
    human_mouse_move(page, click_x, click_y)
    time.sleep(random.randint(300, 800) / 1000)
    page.mouse.click(click_x, click_y)
    print("  已执行 Turnstile checkbox 点击")
    return True


def has_turnstile(page):
    return bool(
        page.locator('input[name="cf-turnstile-response"]').count()
        or page.locator(".cf-turnstile").count()
        or page.locator('iframe[src*="turnstile"], iframe[src*="challenges.cloudflare.com"]').count()
    )


def handle_turnstile(page, context):
    print(f"处理 Cloudflare Turnstile 验证: {context}")
    if wait_for_turnstile_token(page, 20, "自动等待"):
        return True
    if click_turnstile_like_human(page) and wait_for_turnstile_token(page, 30, "人工轨迹点击后等待"):
        return True
    print("  Turnstile 未通过")
    return False


def close_cookie_banner(page):
    candidates = (
        'button:has-text("Accept All")',
        'button:has-text("Accept")',
        'text="Accept All"',
        'text="Accept"',
    )
    for selector in candidates:
        try:
            locator = page.locator(selector)
            if locator.count():
                locator.first.click(timeout=3000, force=True)
                print("已关闭 Cookie 弹窗")
                time.sleep(random.uniform(0.3, 0.8))
                return
        except Exception:
            continue


def login(page):
    print(f"打开登录页面: {LOGIN_URL}")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('input[name="Email"]', timeout=15000)
    close_cookie_banner(page)

    print("填写邮箱...")
    human_type(page.locator('input[name="Email"]'), EMAIL)
    time.sleep(random.uniform(0.3, 0.8))

    print("填写密码...")
    human_type(page.locator('input[name="Password"]'), PASSWORD)
    time.sleep(random.uniform(0.8, 1.5))
    close_cookie_banner(page)

    if has_turnstile(page) and not handle_turnstile(page, "登录页"):
        save_failure_screenshot(page, "login_turnstile_fail.png", "登录失败(Turnstile 未通过)")
        return False

    print("提交登录表单...")
    page.locator('input[name="Password"]').press("Enter")
    try:
        page.wait_for_url(lambda url: "/id/Account/Login" not in url, timeout=15000)
    except PlaywrightTimeoutError:
        page.screenshot(path="login_failed.png", full_page=True)
        return False
    print("登录成功")
    return True


def renew(page):
    global DYNAMIC_APP_NAME

    print("进入控制面板...")
    page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    body_text = page.locator("body").inner_text()
    if "Your account has been restricted" in body_text:
        print("检测到账号限制通知，终止续期。")
        save_failure_screenshot(page, "renew_account_restricted.png", "续期失败(账号已被限制)")
        return False

    cards = page.locator("h3.font-semibold")
    try:
        cards.first.wait_for(timeout=15000)
    except PlaywrightTimeoutError:
        save_failure_screenshot(page, "renew_app_not_found.png", "续期失败(找不到应用)")
        return False

    DYNAMIC_APP_NAME = cards.first.inner_text().strip() or DYNAMIC_APP_NAME
    print(f"读取到应用名称: {DYNAMIC_APP_NAME}")
    cards.first.click()
    time.sleep(3)

    try:
        page.get_by_text("Reset Timer", exact=True).click(timeout=10000)
    except PlaywrightTimeoutError:
        save_failure_screenshot(page, "renew_reset_btn_not_found.png", "续期失败(找不到按钮)")
        return False
    time.sleep(2)

    if has_turnstile(page) and not handle_turnstile(page, "续期弹窗"):
        save_failure_screenshot(page, "renew_turnstile_fail.png", "续期失败(人机验证未过)")
        return False

    try:
        page.get_by_text("Just Reset", exact=True).click(timeout=10000)
    except PlaywrightTimeoutError:
        save_failure_screenshot(page, "renew_just_reset_not_found.png", "续期失败(无法确认)")
        return False

    time.sleep(5)
    page.reload(wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    try:
        timer_text = page.locator("span.font-mono.text-xl").inner_text(timeout=10000).strip()
    except PlaywrightTimeoutError:
        save_failure_screenshot(page, "renew_timer_read_fail.png", "读取剩余时间失败")
        return False

    print(f"当前应用剩余时间: {timer_text}")
    if "2 days 23" in timer_text or "3 days" in timer_text:
        page.screenshot(path="renew_success.png", full_page=True)
        send_tg_message("[OK]", "续期完成", timer_text)
        return True

    page.screenshot(path="renew_warning.png", full_page=True)
    send_tg_message("[!]", "续期异常(请检查)", timer_text)
    send_tg_photo("renew_warning.png", "续期异常(请检查)")
    return False


def main():
    camoufox_path = Path(CAMOUFOX_PATH)
    if not camoufox_path.exists():
        print(f"未找到 Camoufox 浏览器: {camoufox_path}")
        return 1

    proxy = {"server": "http://127.0.0.1:8080"} if PROXY_URL else None

    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            executable_path=str(camoufox_path),
            headless=True,
            proxy=proxy,
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            page.goto("https://api.ipify.org/?format=json", wait_until="domcontentloaded", timeout=30000)
            print(f"当前出口 IP: {page.locator('body').inner_text()}")
        except Exception as exc:
            print(f"出口 IP 检测失败: {exc}")

        try:
            if not login(page):
                return 1
            return 0 if renew(page) else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
