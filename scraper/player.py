"""视频播放器控制：导航、播放、静音、进度监测、心跳上报。"""
import time

from . import api


def play_video(
    context,
    base_url: str,
    activity_id: int,
    course_id: int,
    course_name: str,
    course_code: str,
    jwt_token: str,
    heartbeat_interval: int = 60,
    completion_threshold: int = 80,
    max_duration: int = 1800,
) -> bool:
    """播放单个视频直到完成，返回是否成功。"""
    url = f"{base_url}/course/{course_id}/learning-activity/full-screen#/{activity_id}"
    page = context.new_page()

    try:
        print(f"    加载: ...full-screen#/{activity_id}")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # 等待播放按钮
        try:
            play_btn = page.wait_for_selector("button.mvp-toggle-play", timeout=15000)
            print("    检测到播放器，点击播放")
            play_btn.click()
        except Exception:
            has_video = page.evaluate("() => !!document.querySelector('video')")
            if not has_video:
                print("    未找到视频元素，可能不是视频活动")
                return False

        # 静音
        _mute_video(page)
        page.wait_for_timeout(5000)

        # 获取视频总时长
        duration = page.evaluate(
            "() => { const v = document.querySelector('video'); return v ? Math.floor(v.duration) || 0 : 0; }"
        )

        start_sec = 0
        last_heartbeat = 0
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            progress = _get_progress(page)
            current_sec = int(duration * progress / 100) if duration > 0 else int(elapsed)

            if current_sec - last_heartbeat >= heartbeat_interval:
                end_sec = min(current_sec, duration) if duration > 0 else current_sec
                api.send_heartbeat(context, base_url, activity_id, start_sec, end_sec)

                stats_dur = end_sec - start_sec
                if stats_dur > 0:
                    api.send_video_stats(
                        context, base_url, jwt_token,
                        activity_id, course_id, course_name, course_code,
                        start_sec, end_sec, stats_dur,
                    )
                start_sec = end_sec
                last_heartbeat = end_sec
                print(f"    进度: {progress:.0f}% ({end_sec}s/{duration}s)")

            # 检测完成
            if duration > 0 and current_sec >= duration * 0.95:
                print(f"    视频播完 ({progress:.0f}%)")
                break
            if progress >= completion_threshold:
                print(f"    达到完成阈值 {completion_threshold}% ({progress:.0f}%)")
                break
            if elapsed > max_duration:
                print(f"    超过最大播放时长 {max_duration}s，跳过")
                break

            # 检查是否暂停/结束
            is_ended = page.evaluate("() => { const v = document.querySelector('video'); return v ? v.ended : false; }")
            if is_ended:
                print("    视频已结束")
                break
            is_paused = page.evaluate("() => { const v = document.querySelector('video'); return v ? v.paused : true; }")
            if is_paused and progress > 10:
                try:
                    page.click("button.mvp-toggle-play")
                except Exception:
                    pass

            time.sleep(5)

        # 最终心跳
        final_sec = duration if duration > 0 else int(time.time() - start_time)
        api.send_heartbeat(context, base_url, activity_id, start_sec, final_sec)
        api.send_visit_stats(
            context, base_url, jwt_token,
            activity_id, course_id, course_name, course_code,
            int(time.time() - start_time),
        )
        return True

    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"    播放异常: {e}")
        return False
    finally:
        page.close()


def _mute_video(page) -> None:
    try:
        page.evaluate("() => { const v = document.querySelector('video'); if (v) v.muted = true; }")
    except Exception:
        pass


def _get_progress(page) -> float:
    try:
        width = page.evaluate(
            """() => {
                const el = document.querySelector('.mvp-play-progress');
                if (el) return parseFloat(el.style.width) || 0;
                const v = document.querySelector('video');
                if (v && v.duration) return (v.currentTime / v.duration) * 100;
                return 0;
            }"""
        )
        return float(width)
    except Exception:
        return 0
