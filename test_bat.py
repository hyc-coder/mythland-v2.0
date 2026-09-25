# -*- coding: utf-8 -*-
"""
test_bat.py - build.bat 静态健康检查

历史上 build.bat 反复崩溃，根因全是这几类:
  1. 换行符是 LF（Unix）而不是 CRLF -> cmd 把多行粘连成一行，
     表现出 "'cho' 不是内部或外部命令" 这类诡异报错
  2. UTF-8 带 BOM / Unicode 编码 -> 首行 @echo off 被截断成 'ho'
  3. 中文注释在某代码页下乱码 -> 连带破坏语法
  4. 多行 if/else 括号块 -> "此时不应有 else"

本测试在【打包前】就拦住这些问题，避免用户双击时才炸。

运行: python test_bat.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.path.join(HERE, "build.bat")


def check_bat(path, name):
    """对单个 bat 做核心健康检查，返回问题列表"""
    issues = []
    raw = open(path, "rb").read()

    # 编码 / 换行
    if raw.startswith(b"\xef\xbb\xbf") or raw.startswith(b"\xff\xfe") \
            or raw.startswith(b"\xfe\xff"):
        issues.append(f"{name}: 有 BOM，cmd 会解析坏首行")
    crlf = raw.count(b"\r\n")
    bare_lf = raw.count(b"\n") - crlf
    if bare_lf:
        issues.append(f"{name}: {bare_lf} 处裸 LF —— 必须是 CRLF，否则 cmd 粘连多行")
    na = len([b for b in raw if b > 127])
    if na:
        issues.append(f"{name}: 含 {na} 个非 ASCII 字节，中文在部分代码页下破坏语法")
    if b'cd /d "%~dp0"' not in raw:
        issues.append(f'{name}: 缺 cd /d "%~dp0"，双击时可能定位错目录')

    text = raw.decode("ascii", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")

    # 危险语法
    if re.search(r"(?i)\belse\b", text):
        issues.append(f"{name}: 含 else，多行 if/else 括号易报'此时不应有 else'")
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s.startswith("REM") or s.startswith("::"):
            continue
        if s.count("(") != s.count(")"):
            issues.append(f"{name}: 第 {i} 行括号不配对: {s}")

    # goto 标签
    gotos = {g for g in re.findall(r"(?i)\bgoto\s+(\S+)", text)
             if g.lower() != "eof"}
    labels = {l for l in re.findall(r"^:(\S+)", text, re.M)
              if l.lower() != "eof"}
    missing = gotos - labels
    if missing:
        issues.append(f"{name}: goto 指向未定义标签 {sorted(missing)}")

    # 命令动词白名单（抓住拼写错误，例如把 echo 写成 ho）
    KNOWN = {
        "echo", "rem", "cd", "python", "py", "dir", "pause", "exit",
        "goto", "if", "start", "timeout", "title", "set", "call", "cls",
        "::",
    }
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s.startswith(":") or s.upper().startswith("REM "):
            continue
        verb = s.split()[0].lower().lstrip("@")
        # echo. / echo( / echo: 都是"输出空行"的合法写法，归一成 echo
        if verb.startswith("echo"):
            verb = "echo"
        if verb not in KNOWN:
            issues.append(f"{name}: 第 {i} 行命令动词未知: {verb!r} -> {s[:50]}")

    return issues


def main():
    print("=" * 62)
    print("  bat 脚本静态健康检查")
    print("=" * 62)

    fails = []

    # ---------- 0. 所有 bat 的核心检查 ----------
    print("\n[0] 所有 bat 脚本")
    bats = sorted(f for f in os.listdir(HERE) if f.endswith(".bat"))
    print(f"  发现: {bats}")
    for fn in bats:
        issues = check_bat(os.path.join(HERE, fn), fn)
        if issues:
            for i in issues:
                print(f"  [FAIL] {i}")
            fails.extend(issues)
        else:
            print(f"  [OK] {fn}")
    if not bats:
        fails.append("目录下没有 bat 文件")

    if not os.path.isfile(BAT):
        print("\n  [FAIL] build.bat 不存在，后续检查跳过")
        return 1

    raw = open(BAT, "rb").read()
    text = raw.decode("ascii", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")

    # ---------- 1. 编码 / 换行 ----------
    print("\n[1] 编码与换行（最关键）")

    if raw.startswith(b"\xef\xbb\xbf"):
        fails.append("有 UTF-8 BOM，cmd 会把首行解析坏")
        print("  [FAIL] 检测到 UTF-8 BOM")
    else:
        print("  [OK] 无 BOM")

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        fails.append("是 UTF-16/Unicode 编码，cmd 无法解析")
        print("  [FAIL] 检测到 UTF-16 BOM")
    else:
        print("  [OK] 非 UTF-16")

    crlf = raw.count(b"\r\n")
    bare_lf = raw.count(b"\n") - crlf
    bare_cr = raw.count(b"\r") - crlf
    print(f"  CRLF: {crlf}   裸LF: {bare_lf}   裸CR: {bare_cr}")
    if bare_lf:
        fails.append(f"{bare_lf} 处裸 LF —— 必须是 CRLF，否则 cmd 会粘连多行")
        print("  [FAIL] 存在裸 LF")
    else:
        print("  [OK] 全部 CRLF")
    if bare_cr:
        fails.append("存在裸 CR")
        print("  [FAIL] 存在裸 CR")
    else:
        print("  [OK] 无裸 CR")

    non_ascii = [b for b in raw if b > 127]
    if non_ascii:
        fails.append(f"含 {len(non_ascii)} 个非 ASCII 字节，中文在部分代码页下会破坏语法")
        print(f"  [FAIL] 含非 ASCII 字节: {len(non_ascii)}")
    else:
        print("  [OK] 纯 ASCII（中文不会乱码）")

    text = raw.decode("ascii", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")

    # ---------- 2. 工作目录 ----------
    print("\n[2] 工作目录（双击时容易踩坑）")
    if 'cd /d "%~dp0"' in text:
        print("  [OK] 含 cd /d \"%~dp0\" —— 双击时也能定位到脚本所在目录")
    else:
        fails.append("缺 cd /d \"%~dp0\"：双击时当前目录可能不对，找不到 build.py")
        print("  [FAIL] 缺 cd /d \"%~dp0\"")

    # ---------- 3. 危险语法 ----------
    print("\n[3] 危险语法")
    if re.search(r"(?i)\belse\b", text):
        fails.append("含 else —— cmd 对多行 if/else 括号极敏感，历史上报过'此时不应有 else'")
        print("  [FAIL] 含 else 关键字")
    else:
        print("  [OK] 无 else（用 goto 分支替代）")

    # 未闭合括号（多行括号块）
    bad_brackets = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s.startswith("REM") or s.startswith("::"):
            continue
        if s.count("(") != s.count(")"):
            bad_brackets.append((i, s))
    if bad_brackets:
        fails.append("存在未配对括号（多行括号块易解析失败）")
        for i, s in bad_brackets:
            print(f"  [FAIL] 第 {i} 行括号不配对: {s}")
    else:
        print("  [OK] 括号全部配对，无多行块")

    # ---------- 4. goto 标签 ----------
    print("\n[4] goto 与标签")
    gotos = set(re.findall(r"(?i)\bgoto\s+(\S+)", text))
    labels = set(re.findall(r"^:(\S+)", text, re.M))
    # 排除 :eof
    gotos = {g for g in gotos if g.lower() != "eof"}
    labels = {l for l in labels if l.lower() != "eof"}
    print(f"  goto 目标: {sorted(gotos)}")
    print(f"  已定义标签: {sorted(labels)}")
    missing = gotos - labels
    if missing:
        fails.append(f"goto 指向未定义标签: {sorted(missing)}")
        print(f"  [FAIL] 未定义: {sorted(missing)}")
    else:
        print("  [OK] 所有 goto 都有对应标签")
    unused = labels - gotos
    if unused:
        print(f"  [提示] 定义了但未使用的标签: {sorted(unused)}")

    # ---------- 5. 是否调用 build.py ----------
    print("\n[5] 构建调用")
    if re.search(r"(?i)^\s*python\s+build\.py\s*$", text, re.M):
        print("  [OK] 调用 python build.py")
    else:
        fails.append("没有调用 python build.py")
        print("  [FAIL] 未找到 python build.py")

    # ---------- 6. 产物名一致性 ----------
    print("\n[6] 产物名一致性（build.py vs bat 提示）")
    try:
        sys.path.insert(0, HERE)
        import build as B
        src = open(os.path.join(HERE, "build.py"), encoding="utf-8").read()
        for nm in ("controller", "agent", "agent-debug"):
            if f'"{nm}"' in src:
                print(f"  [OK] build.py 产物含 {nm}")
            else:
                fails.append(f"build.py 未生成 {nm}")
                print(f"  [FAIL] build.py 缺 {nm}")
        # bat 提示里也应出现
        for nm in ("controller.exe", "agent.exe", "agent-debug.exe"):
            if nm in text:
                print(f"  [OK] bat 提示含 {nm}")
            else:
                print(f"  [提示] bat 提示未列出 {nm}")
    except Exception as e:
        fails.append(f"无法导入 build.py: {e}")
        print(f"  [FAIL] 导入 build.py 失败: {e}")

    # ---------- 7. build.py 语法 ----------
    print("\n[7] build.py 语法")
    try:
        with open(os.path.join(HERE, "build.py"), encoding="utf-8") as f:
            compile(f.read(), "build.py", "exec")
        print("  [OK] build.py 语法正确")
    except SyntaxError as e:
        fails.append(f"build.py 语法错误: {e}")
        print(f"  [FAIL] {e}")

    # ---------- 结果 ----------
    print("\n" + "=" * 62)
    if fails:
        print(f"  发现 {len(fails)} 个问题:")
        for f in fails:
            print(f"   - {f}")
        print("  build.bat 不可靠，请修复后再分发")
        print("=" * 62)
        return 1
    print("  全部检查通过 ✓  build.bat 可以安全双击运行")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
