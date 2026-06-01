import base64
import json
import os

import sys

from playwright.sync_api import sync_playwright


def _launch_browser(p, headless: bool = True):
    """启动 Chromium 浏览器，优先复用系统已安装的 Chrome/Edge。"""
    args = ["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"]
    for channel, name in [("chrome", "Chrome"), ("msedge", "Edge"), (None, "Chromium")]:
        try:
            launch_args = {"headless": headless, "args": args}
            if channel:
                launch_args["channel"] = channel
            return p.chromium.launch(**launch_args)
        except Exception as e:
            last_error = e

    if "Executable doesn't exist" in str(last_error):
        print(f"\n未找到可用浏览器，请安装 Chrome/Edge 或运行:\n  playwright install chromium\n")
    else:
        print(f"启动浏览器失败: {last_error}")
    sys.exit(1)


def _creds_path(data_dir: str) -> str:
    return os.path.join(data_dir, "credentials.json")


def state_file_exists(state_path: str) -> bool:
    return os.path.exists(state_path)


# ── 账号管理 ──────────────────────────────────────────

# 注意：密码以 base64 存储，仅作简单混淆（非加密），文件本身应通过系统权限保护
def save_credentials(data_dir: str, account: str, username: str, password: str) -> None:
    os.makedirs(data_dir, exist_ok=True)
    path = _creds_path(data_dir)
    data = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[account] = {
        "username": username,
        "password": base64.b64encode(password.encode()).decode(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"账号 '{account}' 已保存 ({username})")


def load_credentials(data_dir: str, account: str) -> dict | None:
    path = _creds_path(data_dir)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entry = data.get(account)
    if not entry:
        return None
    return {
        "username": entry["username"],
        "password": base64.b64decode(entry["password"]).decode(),
    }


def list_accounts(data_dir: str) -> list[str]:
    path = _creds_path(data_dir)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(json.load(f).keys())


def delete_credentials(data_dir: str, account: str) -> bool:
    path = _creds_path(data_dir)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if account not in data:
        return False
    del data[account]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"账号 '{account}' 已删除")
    return True


# ── 登录 ──────────────────────────────────────────────

def login_and_save_state(base_url: str, state_path: str) -> None:
    """打开浏览器让用户手动登录。"""
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with sync_playwright() as p:
        browser = _launch_browser(p, headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="zh-CN")
        page = context.new_page()
        print("正在打开登录页面...")
        page.goto(f"{base_url}/user/index", timeout=30000)
        print("请在浏览器中完成登录...")
        try:
            page.wait_for_url(f"{base_url}/user/index#/", timeout=300000)
        except Exception:
            print("等待超时，请确认是否已完成登录。")
        page.wait_for_timeout(3000)
        context.storage_state(path=state_path)
        print(f"登录状态已保存到: {state_path}")
        browser.close()


def auto_login(base_url: str, username: str, password: str, state_path: str) -> tuple[bool, str]:
    """自动填充 XMU CAS 认证表单并登录。成功返回 (True, 用户姓名)。"""
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with sync_playwright() as p:
        browser = _launch_browser(p, headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="zh-CN")
        page = context.new_page()
        try:
            print("正在自动登录...")
            page.goto(f"{base_url}/user/index", timeout=30000)
            page.wait_for_timeout(3000)

            try:
                page.click("text=账号登录", timeout=3000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            page.fill('input[placeholder="请输入学号/工号"]', username)
            page.fill('input[name="passwordText"]', password)

            captcha_input = page.locator("#captcha")
            if captcha_input.is_visible():
                captcha_val = captcha_input.input_value()
                captcha_img = page.locator("img[src*='captcha']")
                if captcha_img.is_visible() and not captcha_val:
                    print("需要验证码，无法自动登录。请手动执行 python main.py --login")
                    browser.close()
                    return False, ""

            page.click("div.btn:has-text('登录'):not(:has(input))")
            page.keyboard.press("Enter")

            try:
                page.wait_for_url(f"{base_url}/user/index#/", timeout=60000)
            except Exception:
                print("自动登录失败，请检查账号密码或是否需要验证码。")
                browser.close()
                return False, ""

            page.wait_for_timeout(3000)

            # 提取姓名
            user_name = ""
            try:
                user_name = page.text_content("#userCurrentName", timeout=5000) or ""
                user_name = user_name.strip()
            except Exception:
                pass

            context.storage_state(path=state_path)
            print(f"自动登录成功 -> {user_name}")
            browser.close()
            return True, user_name
        except Exception as e:
            print(f"自动登录异常: {e}")
            browser.close()
            return False, ""


# ── session 管理 ──────────────────────────────────────

def create_context(state_path: str, headless: bool = True):
    if not os.path.exists(state_path):
        raise FileNotFoundError(
            f"未找到登录状态文件: {state_path}\n请先运行: python main.py --login")
    playwright = sync_playwright().start()
    browser = _launch_browser(playwright, headless=headless)
    context = browser.new_context(
        storage_state=state_path,
        viewport={"width": 1280, "height": 800}, locale="zh-CN")
    return playwright, browser, context


def check_session_valid(context, base_url: str) -> bool:
    page = context.new_page()
    try:
        page.goto(f"{base_url}/user/index", timeout=15000)
        page.wait_for_timeout(2000)
        if "c-identity" in page.url or "auth" in page.url.lower():
            return False
        return True
    except Exception:
        return False
    finally:
        page.close()
