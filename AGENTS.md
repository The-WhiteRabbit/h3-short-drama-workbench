# 项目说明

- 主代码目录：scripts/ 为 Skill 工具；assets/local_review/ 为复制到新项目的审核服务；reference/ 为使用协议。
- 启动命令：`python scripts/h3_project.py init /新项目目录 --title 项目名 --start`；已有项目使用 `python scripts/h3_project.py start /项目目录`。
- 测试命令：`python -m unittest discover -s assets/local_review -p 'test_*.py'`；`python scripts/h3_assets_tests.py`；Skill 格式校验使用系统 skill-creator/scripts/quick_validate.py。
- 构建命令：无需构建，Python 脚本与 HTML 模板直接使用。
- 不允许修改：用户项目素材、人工审核结论、凭据；测试不得发起真实生成。
- 完成标准：修改对应回归测试通过，安装版与维护源码相关文件一致；不覆盖已有项目 service 的独立改动。
- 大日志只输出错误和最后 100 行。
