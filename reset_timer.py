#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import random
import sys
import time
from pathlib import Path

import requests
from DrissionPage import Chromium, ChromiumOptions

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
PANEL_URL = "https://justrunmy.app/panel"

EMAIL = os.environ.get("ACC")
PASSWORD = os.environ.get("ACC_PWD")
TG_BOT_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_ID")
RUN_ATTEMPT = os.environ.get("RUN_ATTEMPT", "").strip()
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
BROWSER_PATH = os.environ.get("BROWSER_PATH", "").strip()
PATCH_DIR = Path(os.environ.get("PATCH_DIR", "turnstilePatch")).resolve()

if not EMAIL or not PASSWORD:
    print("致命错误：未找到 ACC 或 ACC_PWD 环境变量")
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
    page.get_screenshot(path=image_path, full_page=True)
    send_tg_message("[X]", status_text, time_left)
    send_tg_photo(image_path, status_text)


def sleep_random(min_seconds, max_seconds):
    time.sleep(random.uniform(min_seconds, max_seconds))


def page_text(page):
    try:
        return page.ele("tag:body").text or ""
    except Exception:
        return ""


def token_value(page):
    return page.run_js(
        """
        const input = document.querySelector('input[name="cf-turnstile-response"]');
        return input ? input.value : '';
        """
    ) or ""


def turnstile_failed(page):
    text = page_text(page).lower()
    return "verification failed" in text or "验证失败" in text


def has_turnstile(page):
    try:
        return bool(page.ele("@name=cf-turnstile-response", timeout=1))
    except Exception:
        return False


def click_turnstile_shadow_input(page):
    challenge_solution = page.ele("@name=cf-turnstile-response", timeout=3)
    challenge_wrapper = challenge_solution.parent()
    challenge_iframe = challenge_wrapper.shadow_root.ele("tag:iframe", timeout=3)
    challenge_iframe.run_js(
        """
        function getRandomInt(min, max) {
            return Math.floor(Math.random() * (max - min + 1)) + min;
        }
        Object.defineProperty(MouseEvent.prototype, 'screenX', { value: getRandomInt(800, 1200) });
        Object.defineProperty(MouseEvent.prototype, 'screenY', { value: getRandomInt(400, 600) });
        """
    )
    challenge_body = challenge_iframe.ele("tag:body").shadow_root
    challenge_button = challenge_body.ele("tag:input", timeout=3)
    challenge_button.click()


def handle_turnstile(page, context):
    print(f"处理 Cloudflare Turnstile 验证: {context}")
    deadline = time.time() + 35
    clicked = False

    while time.time() < deadline:
        token = token_value(page)
        if len(token) > 20:
            print("  Turnstile 已通过")
            return True
        if turnstile_failed(page):
            print("  Turnstile 已明确失败")
            return False

        if not clicked:
            try:
                click_turnstile_shadow_input(page)
                clicked = True
                print("  已执行 Turnstile shadow DOM 点击")
            except Exception as exc:
                print(f"  暂未拿到可点击节点: {exc}")

        time.sleep(1)

    print("  Turnstile 未通过")
    return False


def close_cookie_banner(page):
    for text in ("Accept All", "Accept"):
        try:
            button = page.ele(f"text:{text}", timeout=1)
            if button:
                button.click()
                print("已关闭 Cookie 弹窗")
                sleep_random(0.3, 0.8)
                return
        except Exception:
            continue


def human_type(element, text):
    element.clear()
    for char in text:
        element.input(char, clear=False)
        time.sleep(random.uniform(0.05, 0.15))


def login(page):
    print(f"打开登录页面: {LOGIN_URL}")
    page.get(LOGIN_URL)
    page.ele("@name=Email", timeout=15)
    close_cookie_banner(page)

    print("填写邮箱...")
    human_type(page.ele("@name=Email"), EMAIL)
    sleep_random(0.3, 0.8)

    print("填写密码...")
    human_type(page.ele("@name=Password"), PASSWORD)
    sleep_random(0.8, 1.5)
    close_cookie_banner(page)

    if has_turnstile(page) and not handle_turnstile(page, "登录页"):
        save_failure_screenshot(page, "login_turnstile_fail.png", "登录失败(Turnstile 未通过)")
        return False

    print("提交登录表单...")
    page.ele("@name=Password").input("\n", clear=False)
    deadline = time.time() + 20
    while time.time() < deadline:
        if "/id/Account/Login" not in page.url:
            print("登录成功")
            return True
        time.sleep(1)

    save_failure_screenshot(page, "login_failed.png", "登录失败")
    return False


def renew(page):
    global DYNAMIC_APP_NAME

    print("进入控制面板...")
    page.get(PANEL_URL)
    time.sleep(5)

    body_text = page_text(page)
    if "Your account has been restricted" in body_text:
        print("检测到账号限制通知，终止续期。")
        save_failure_screenshot(page, "renew_account_restricted.png", "续期失败(账号已被限制)")
        return False

    cards = page.eles("css:h3.font-semibold")
    if not cards:
        save_failure_screenshot(page, "renew_app_not_found.png", "续期失败(找不到应用)")
        return False

    DYNAMIC_APP_NAME = cards[0].text.strip() or DYNAMIC_APP_NAME
    print(f"读取到应用名称: {DYNAMIC_APP_NAME}")
    cards[0].click()
    time.sleep(3)

    reset_button = page.ele("text:Reset Timer", timeout=10)
    if not reset_button:
        save_failure_screenshot(page, "renew_reset_btn_not_found.png", "续期失败(找不到按钮)")
        return False
    reset_button.click()
    time.sleep(2)

    if has_turnstile(page) and not handle_turnstile(page, "续期弹窗"):
        save_failure_screenshot(page, "renew_turnstile_fail.png", "续期失败(人机验证未过)")
        return False

    just_reset = page.ele("text:Just Reset", timeout=10)
    if not just_reset:
        save_failure_screenshot(page, "renew_just_reset_not_found.png", "续期失败(无法确认)")
        return False
    just_reset.click()

    time.sleep(5)
    page.refresh()
    time.sleep(4)

    timer = page.ele("css:span.font-mono.text-xl", timeout=10)
    if not timer:
        save_failure_screenshot(page, "renew_timer_read_fail.png", "读取剩余时间失败")
        return False

    timer_text = timer.text.strip()
    print(f"当前应用剩余时间: {timer_text}")
    if "2 days 23" in timer_text or "3 days" in timer_text:
        page.get_screenshot(path="renew_success.png", full_page=True)
        send_tg_message("[OK]", "续期完成", timer_text)
        return True

    page.get_screenshot(path="renew_warning.png", full_page=True)
    send_tg_message("[!]", "续期异常(请检查)", timer_text)
    send_tg_photo("renew_warning.png", "续期异常(请检查)")
    return False


def build_browser_options():
    options = ChromiumOptions()
    options.auto_port()
    options.set_argument("--window-size=1440,900")
    options.add_extension(str(PATCH_DIR))
    if BROWSER_PATH:
        options.set_browser_path(BROWSER_PATH)
    if HEADLESS:
        options.headless()
    if PROXY_URL:
        options.set_proxy("http://127.0.0.1:8080")
    return options


def main():
    if not PATCH_DIR.exists():
        print(f"未找到 Turnstile 补丁扩展: {PATCH_DIR}")
        return 1

    browser = Chromium(build_browser_options())
    page = browser.latest_tab

    try:
        try:
            page.get("https://api.ipify.org/?format=json")
            print(f"当前出口 IP: {page_text(page)}")
        except Exception as exc:
            print(f"出口 IP 检测失败: {exc}")

        if not login(page):
            return 1
        return 0 if renew(page) else 1
    finally:
        browser.quit()


if __name__ == "__main__":
    sys.exit(main())
