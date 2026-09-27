# QuickMUD 汉化 (i18n) TODO

> 最后更新：2026-09-27  
> 当前覆盖率：**100.0%**（858/858 玩家可见字符串）

---

## 已完成

### 翻译框架
- [x] `t()` 精确匹配 → 正则模式匹配 → 英文回退 三级翻译管道
- [x] 正则模式惰性编译与缓存 (`_compiled_patterns`)
- [x] 语言偏好持久化（`pcdata.language` → DB → 恢复）
- [x] `LANGUAGE=zh` 环境变量 + `.env` dotenv 加载
- [x] 延迟初始化（解决 dotenv 加载时序问题）
- [x] 测试隔离（`_force_english` autouse fixture）

### 内容翻译
| 类别 | 总量 | 覆盖率 | 备注 |
|------|------|--------|------|
| 房间描述 | 3128 | 100% | 核心区域高质量，批量翻译区域待改进 |
| 物品名称/描述 | 1285 | 100% | 单词替换法，部分待人工润色 |
| 怪物名称/描述 | 986 | 100% | 同上 |
| 技能名称 | 134 | 100% | — |
| 帮助主题 | 249 | 100% | 45 个实质性主题已人工翻译 |
| 社交模板 | 851 | 100% | 含代词转换 |
| 系统消息 | ~1040 | 100% | 精确匹配 + 正则模式 |
| 正则模式 | ~100 | — | 覆盖动态 f-string |

### 子系统翻译
- [x] 移动命令（north/south/enter/leave 等）
- [x] 查看命令（look/examine/peek 等）
- [x] 物品命令（get/drop/put/wear/remove 等）
- [x] 战斗消息（hit/miss/damage/spell 等）
- [x] 商店系统（buy/sell/list/value 等）
- [x] 训练/练习（practice/train/gain 等）
- [x] 位置命令（stand/sit/rest/sleep/wake 等）
- [x] 通讯命令（say/tell/shout/gossip 等）
- [x] 小组命令（group/follow/leader 等）
- [x] 配置命令（config/terminal/prompt 等）
- [x] Prompt 系统（alignment word / exits token）
- [x] Score 面板（10 个正则模式 + 条件消息）
- [x] 液体/容器（fill/drink/pour 等）
- [x] 盗贼技能（steal/sneak/hide 等）
- [x] 别名系统（alias/unalias）
- [x] 自动设置（autoloot/autosac 等）
- [x] 笔记系统（notes/read/note 等）

### 审计工具
- [x] `scripts/i18n_coverage.py` — 覆盖率审计（转义解码 + 假阳性过滤）
- [x] `scripts/i18n_extract_missing.py` — 未翻译字符串提取

---

## 待完成

### P1 — 质量提升

#### 翻译质量润色
- [ ] **批量翻译区域人工审查**：单词替换法生成的房间/物品/怪物描述存在中英混杂、语法不通顺的问题。优先审查新手路线（Midgaard 城区、学校、下水道）。
- [ ] **帮助主题质量提升**：剩余 ~134 个帮助主题多为技能/法术语法条目，命令名保留英文正确，但描述部分可改进可读性。
- [ ] **社交模板润色**：~720 个社交模板使用机器翻译，常见动作（smile/laugh/hug 等 ~130 个）已人工翻译，其余待审查。

#### 翻译一致性
- [ ] 统一术语表：确保同一概念在不同模块中使用相同的中文翻译（如 "mana" → "法力" 而非混用 "魔法值"）。
- [ ] 统一称谓：NPC 对玩家的称呼统一（"你" vs "您"）。

### P2 — 功能增强

#### 结构化 UI 翻译
- [ ] `do_config` 面板：config 命令的显示输出目前部分翻译，需要完善所有配置项的标签翻译。
- [ ] `do_affects` 面板：affects 显示的法术效果名称/描述翻译。
- [ ] `do_equipment` 面板：装备位置名称翻译（已在 look.py 中部分实现）。

#### 动态消息完善
- [ ] f-string 直接翻译支持：当前 f-string 需通过正则模式匹配，如果能在代码中直接调用 `t()` 会更可靠。需要逐模块改造。
- [ ] `act_format()` 模板翻译扩展：更多 act() 调用中的 `$n/$p` 模板需要翻译条目。

### P3 — 基础设施

#### 测试覆盖
- [ ] 编写集成测试验证命令返回值在 `LANGUAGE=zh` 时被翻译。
- [ ] 为正则模式翻译添加边界测试（负数、零值、特殊字符）。

#### 审计自动化
- [ ] CI 集成 `i18n_coverage.py`：在 PR 检查中运行覆盖率审计，确保新增字符串被翻译。
- [ ] 翻译质量评分脚本：自动检测中英混杂、语法异常。

---

## 已知问题

### 双转义修复（已修复）
zh.json 中曾有 37 个 key 使用 `\\n`（字面反斜杠+n）而非 `\n`（实际换行），导致运行时永远无法匹配。已通过修复脚本统一修正。

### Windows 平台测试
- `test_do_time_command.py::test_basic_time_display` 因 `strftime("%-d")` 在 Windows 不支持而失败（预存问题，非 i18n 相关）。
- 全量串行测试有 12 个预存跨测试状态泄漏失败（单独运行均通过）。

### Prompt 出口字母
Prompt 中的出口方向使用单字母缩写（N/E/S/W/U/D），这是 MUD 标准惯例，中文模式下保持不变。仅 "none" 翻译为 "无"。

---

## 运行审计

```bash
# 覆盖率审计
python scripts/i18n_coverage.py

# JSON 格式输出
python scripts/i18n_coverage.py --json

# 带阈值检查（CI 用）
python scripts/i18n_coverage.py --threshold 95
```
