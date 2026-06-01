# XMU 课程网视频辅助工具

按课程大纲顺序自动播放未完成的视频任务，直到完成度达标。

## 免责声明

本项目仅供学习和研究使用。请遵守课程平台的使用条款，合理使用自动化工具。使用者自行承担因使用本工具产生的一切后果。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 保存账号（自动识别姓名）
python main.py --save-cred

# 3. 编辑 config.yaml：填入 course_ids
#    获取方式：点进课程页面，从 URL 中提取 course_id
#    https://lnt.xmu.edu.cn/course/87713/index#/
#                                  ^^^^^ 填这个数字

# 4. 运行
python main.py --run
```

## 账号管理

```bash
# 保存账号（自动登录后提取姓名作为账号名）
python main.py --save-cred

# 切换账号（列出序号，输入数字选择）
python main.py --switch

# 手动登录
python main.py --login
```

## 配置说明

```yaml
# config.yaml
base_url: "https://lnt.xmu.edu.cn"

course_ids:           # 要刷的课程 ID 列表
  - 87713             

video:
  heartbeat_interval: 60    # 心跳上报间隔（秒）
  completion_threshold: 90  # 完成度阈值（%），达到即跳过
  max_duration: 1800        # 单个视频最大播放时长（秒），防卡死

auth:
  state_file: "./data/auth_state.json"
  jwt_token: "..."          # 统计 API 的 JWT，从视频页 XHR 提取

browser:
  headless: true            # false 可观察播放过程
```

## 工作原理

```
--run 流程：
  1. 加载/刷新登录态
  2. 获取活动列表 → 筛选 online_video 且未完成
  3. 按大纲顺序排序（syllabus_id → sort）
  4. 逐个：打开 → 点播放 → 静音 → 每60s报进度 → 达标切下一个
```

## 文件结构

```
xmu-video-autoplay/
├── main.py              入口
├── config.yaml           配置文件
├── requirements.txt      依赖
├── scraper/
│   ├── auth.py           登录 / CAS 认证 / 浏览器管理
│   ├── api.py            活动 API + 完成度查询 + 心跳上报
│   └── player.py         视频播放器控制
└── data/                 登录态、凭据（本地不提交）
```

## 注意事项

- **jwt_token 自动提取**：首次播放视频时自动从页面 XHR 请求中截取，无需手动配置
- 浏览器优先用系统 Chrome/Edge，无需额外安装 Chromium
- 隔壁项目已登录的话直接复制 `data/auth_state.json` 即可
