"""课程网 API 调用：活动列表、完成度、心跳上报。
POST 请求使用 Python requests + 浏览器 cookie，避免 JavaScript fetch 问题。"""
import time

import requests


def _get_cookies(context) -> dict[str, str]:
    """从 Playwright 上下文中提取 cookie 字典。"""
    return {c["name"]: c["value"] for c in context.cookies()}


def _api_get_json(context, url: str) -> dict:
    """用 Playwright 上下文调用 API，返回 JSON。"""
    page = context.new_page()
    try:
        resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
        if resp and resp.ok:
            return resp.json()
        if resp:
            print(f"  [WARN] API {resp.status}: {url}")
        return {}
    except Exception as e:
        print(f"  [WARN] API 异常: {url} ({e})")
        return {}
    finally:
        page.close()


def fetch_activities(context, base_url: str, course_id: int) -> list[dict]:
    """获取课程全部活动。"""
    data = _api_get_json(context, f"{base_url}/api/courses/{course_id}/activities")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("activities") or data.get("data") or []
    return []


def fetch_completeness(context, base_url: str, course_id: int) -> dict[int, int]:
    """获取课程完成度，返回 {activity_id: completeness}。"""
    data = _api_get_json(context, f"{base_url}/api/courses/{course_id}/learning-task-stat")
    items = data.get("completeness", []) if isinstance(data, dict) else []
    return {int(it["activity_id"]): it.get("completeness", 0) for it in items}


def send_heartbeat(context, base_url: str, activity_id: int, start_sec: int, end_sec: int) -> bool:
    """POST /api/course/activities-read/{id}，上报播放进度。"""
    try:
        url = f"{base_url}/api/course/activities-read/{activity_id}"
        resp = requests.post(
            url, json={"start": start_sec, "end": end_sec},
            cookies=_get_cookies(context), timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"  [WARN] 心跳失败 activity={activity_id}: {e}")
        return False


def send_video_stats(
    context, base_url: str, jwt_token: str,
    activity_id: int, course_id: int, course_name: str, course_code: str,
    start_at: int, end_at: int, duration: int,
    module_id: int = 0, syllabus_id: int = 0,
) -> bool:
    """POST /statistics/api/online-videos，上报播放统计。"""
    try:
        url = f"{base_url}/statistics/api/online-videos?jwt={jwt_token}"
        body = {
            "action_type": "play",
            "activity_id": activity_id, "course_id": course_id,
            "course_name": course_name, "course_code": course_code,
            "module_id": module_id, "syllabus_id": syllabus_id,
            "start_at": start_at, "end_at": end_at, "duration": duration,
            "dep_code": "", "dep_id": "", "dep_name": "",
            "is_student": True, "is_teacher": False,
            "meeting_type": "online_video",
            "org_code": "xmu", "org_id": 1, "org_name": "课程中心",
            "upload_id": 0, "user_id": 0, "user_name": "", "user_no": "",
            "comment_id": None, "forum_type": "", "reply_id": None,
            "ts": int(time.time() * 1000), "user_agent": "",
        }
        resp = requests.post(url, json=body, cookies=_get_cookies(context), timeout=10)
        return resp.ok
    except Exception as e:
        print(f"  [WARN] 视频统计上报失败: {e}")
        return False


def send_visit_stats(
    context, base_url: str, jwt_token: str,
    activity_id: int, course_id: int, course_name: str, course_code: str,
    visit_duration: int,
) -> bool:
    """POST /statistics/api/user-visits，上报访问统计。"""
    try:
        url = f"{base_url}/statistics/api/user-visits?jwt={jwt_token}"
        body = {
            "activity_id": activity_id, "activity_type": "online_video",
            "course_id": course_id, "course_name": course_name, "course_code": course_code,
            "visit_duration": visit_duration, "auto_interval": True,
            "dep_code": "", "dep_id": "", "dep_name": "",
            "is_teacher": False,
            "org_code": "xmu", "org_id": 1, "org_name": "课程中心",
            "user_id": "", "user_name": "", "user_no": "",
            "visit_start_from": "", "user_agent": "", "browser": "",
        }
        resp = requests.post(url, json=body, cookies=_get_cookies(context), timeout=10)
        return resp.ok
    except Exception as e:
        print(f"  [WARN] 访问统计上报失败: {e}")
        return False


def extract_jwt(context, base_url: str, course_id: int, activity_id: int) -> str:
    """从视频页自动提取 JWT token（拦截统计 API 请求）。"""
    url = f"{base_url}/course/{course_id}/learning-activity/full-screen#/{activity_id}"

    jwt_value: str = ""

    def _on_response(response):
        nonlocal jwt_value
        if not jwt_value and "statistics/api" in response.url and "jwt=" in response.url:
            try:
                from urllib.parse import urlparse, parse_qs
                jwt_value = parse_qs(urlparse(response.url).query).get("jwt", [""])[0]
            except Exception:
                pass

    page = context.new_page()
    page.on("response", _on_response)
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)  # 等待 XHR 发出
        if jwt_value:
            print("    已自动提取 JWT")
        else:
            print("    [WARN] 未能从页面提取 JWT")
    except Exception as e:
        print(f"    [WARN] JWT 提取异常: {e}")
    finally:
        page.close()
    return jwt_value
