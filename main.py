"""XMU 课程网视频辅助工具

按顺序自动播放指定课程中未完成的视频任务。

用法:
  python main.py --login              手动登录，保存会话
  python main.py --run                 自动刷课
  python main.py --save-cred           保存账号密码
  python main.py --account <名称>     切换账号
"""

import argparse
import os
import sys

import yaml

from scraper import auth, api, player


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _data_dir(config: dict) -> str:
    return os.path.dirname(config["auth"]["state_file"]) or "./data"


def _active_account(config: dict) -> str:
    return config.get("auth", {}).get("account", "default")


def _try_auto_login(config: dict) -> bool:
    data_dir = _data_dir(config)
    account = _active_account(config)
    creds = auth.load_credentials(data_dir, account)
    if not creds:
        print(f"未找到账号 '{account}' 的凭据，请先保存: python main.py --save-cred")
        return False
    return auth.auto_login(
        config["base_url"], creds["username"], creds["password"],
        config["auth"]["state_file"],
    )


def cmd_login(config: dict) -> None:
    auth.login_and_save_state(config["base_url"], config["auth"]["state_file"])


def cmd_list_accounts(config: dict) -> None:
    accounts = auth.list_accounts(_data_dir(config))
    if not accounts:
        print("未保存任何账号，请先执行: python main.py --save-cred")
        return
    active = _active_account(config)
    for a in accounts:
        marker = " *" if a == active else ""
        print(f"  {a}{marker}")


def cmd_save_cred(config: dict) -> None:
    account = _active_account(config)
    username = input("学号/工号: ").strip()
    password = input("密码: ").strip()
    if not username or not password:
        print("用户名和密码不能为空")
        return
    auth.save_credentials(_data_dir(config), account, username, password)


def cmd_run(config: dict) -> None:
    base_url = config["base_url"]
    state_path = config["auth"]["state_file"]
    headless = config["browser"].get("headless", True)
    jwt_token = config["auth"].get("jwt_token", "")
    course_ids = config.get("course_ids", [])
    vcfg = config.get("video", {})

    if not course_ids:
        print("未配置 course_ids，请在 config.yaml 中设置")
        return

    if not auth.state_file_exists(state_path):
        print("未找到登录状态，尝试自动登录...")
        if not _try_auto_login(config):
            return

    pw, browser, context = auth.create_context(state_path, headless=headless)

    try:
        if not auth.check_session_valid(context, base_url):
            print("会话已过期，尝试自动登录...")
            context.close()
            browser.close()
            pw.stop()
            if not _try_auto_login(config):
                return
            pw, browser, context = auth.create_context(state_path, headless=headless)

        for course_id in course_ids:
            print(f"\n{'=' * 50}")
            print(f"课程 ID: {course_id}")

            activities = api.fetch_activities(context, base_url, course_id)
            completeness = api.fetch_completeness(context, base_url, course_id)

            videos = [
                a for a in activities
                if a.get("type") == "online_video"
                and completeness.get(a.get("id", 0), 0) < 100
            ]
            videos.sort(key=lambda a: (a.get("syllabus_id", 0), a.get("sort", 0)))
            print(f"  共 {len(videos)} 个未完成视频")

            course_name = ""
            course_code = ""
            completed = 0
            for v in videos:
                aid = v["id"]
                title = v.get("title", "")
                course_name = course_name or v.get("course_name", "")
                course_code = course_code or v.get("course_code", "")
                comp = completeness.get(aid, 0)

                print(f"  [{completed + 1}/{len(videos)}] {title} (完成度: {comp}%)")

                jwt_token = api.extract_jwt(context, base_url, course_id, aid)

                ok = player.play_video(
                    context, base_url, aid, course_id,
                    course_name, course_code, jwt_token,
                    vcfg.get("heartbeat_interval", 60),
                    vcfg.get("completion_threshold", 80),
                    vcfg.get("max_duration", 1800),
                )
                if ok:
                    completed += 1
                    print(f"    完成!")
                else:
                    print(f"    失败/跳过")

            print(f"\n  完成: {completed}/{len(videos)}")
            context.storage_state(path=state_path)

    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="XMU 课程网视频自动刷课")
    parser.add_argument("--login", action="store_true", help="手动登录并保存会话")
    parser.add_argument("--run", action="store_true", help="开始自动刷课")
    parser.add_argument("--save-cred", action="store_true", help="保存账号密码")
    parser.add_argument("--account", type=str, metavar="NAME", help="切换/指定账号")
    parser.add_argument("--list-accounts", action="store_true", help="列出已保存账号")
    args = parser.parse_args()

    config = load_config()
    if args.account:
        config["auth"]["account"] = args.account

    if args.save_cred:
        cmd_save_cred(config)
    if args.login:
        cmd_login(config)
    if args.list_accounts:
        cmd_list_accounts(config)
    if args.run:
        cmd_run(config)

    if not any([args.login, args.run, args.save_cred, args.list_accounts]):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
