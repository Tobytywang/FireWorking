# _skill_probe

WorkBuddy 已安装 skill **`shader-dev`** 的本地探查副本(离线快照),用于研读其能力边界与 GLSL 实现,**不改动原 skill**。

## 结构

- `skills/shader-dev/SKILL.md` —— skill 入口:名称、描述、36 项 GLSL 技术清单、调用方式。
- `skills/shader-dev/reference/` —— 各项着色器技术(GLSL:ray marching / SDF / fluid / particle / procedural / lighting / post-processing 等)的参考文档。
- 共 75 个 `.md`。

## 用途

- 对照 `shader-dev` 的能力边界,作为本地参考,避免反复翻阅 WorkBuddy skill 缓存。
- 离线研究 GLSL 技法实现细节。

## 说明

- 这是**副本**:更新需回源头 skill(`~/.workbuddy/.../skills/shader-dev/`),本目录不反向同步。
- 纳入 git 仅为留档,不参与任何构建。
- 项目根 `README.md` 留给 keyboard-heat 等真正项目说明;本目录的说明单独放在这里。
