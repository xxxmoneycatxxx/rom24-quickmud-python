"""Automated i18n smoke test: connect via TCP, create a character, run key commands."""
from __future__ import annotations

import asyncio
import re
import sys

HOST = "localhost"
PORT = 5100
CHAR_NAME = "Testchar"
PASSWORD = "testpass123"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\{[a-zA-Z]")
TELNET_RE = re.compile(r"\xff[\xf9\xfb\xfc\xfd\xfe]")


def strip_ansi(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = TELNET_RE.sub("", text)
    # Remove null bytes
    text = text.replace("\x00", "")
    return text


async def read_until(reader: asyncio.StreamReader, marker: str, timeout: float = 10.0) -> str:
    """Read until we see a specific marker string."""
    buf = b""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            chunk = await asyncio.wait_for(reader.read(8192), timeout=1.5)
            if not chunk:
                break
            buf += chunk
            decoded = strip_ansi(buf.decode("utf-8", errors="replace"))
            if marker in decoded:
                break
        except asyncio.TimeoutError:
            break
    return strip_ansi(buf.decode("utf-8", errors="replace"))


async def read_all(reader: asyncio.StreamReader, timeout: float = 2.0) -> str:
    """Read all available data within timeout."""
    buf = b""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            chunk = await asyncio.wait_for(reader.read(8192), timeout=1.0)
            if not chunk:
                break
            buf += chunk
        except asyncio.TimeoutError:
            break
    return strip_ansi(buf.decode("utf-8", errors="replace"))


async def send(writer: asyncio.StreamWriter, text: str) -> None:
    writer.write((text + "\n").encode("utf-8"))
    await writer.drain()
    await asyncio.sleep(0.3)


async def main() -> None:
    print(f"[CONNECT] {HOST}:{PORT}")
    reader, writer = await asyncio.open_connection(HOST, PORT)

    # Step 1: Wait for ANSI prompt
    ansi_prompt = await read_until(reader, "(Y/n)", timeout=5.0)
    print(f"\n{'='*60}")
    print("[1] ANSI PROMPT")
    print(f"{'='*60}")
    print(ansi_prompt)

    # Answer N for no ANSI (cleaner output)
    await send(writer, "N")

    # Step 2: Wait for greeting + name prompt
    greeting = await read_until(reader, "名字", timeout=5.0)
    print(f"\n{'='*60}")
    print("[2] GREETING + NAME PROMPT")
    print(f"{'='*60}")
    print(greeting)

    # Step 3: Send character name
    await send(writer, CHAR_NAME)

    # Wait for name confirmation prompt
    name_resp = await read_until(reader, "(Y/N)", timeout=5.0)
    print(f"\n{'='*60}")
    print("[3] NAME CONFIRMATION")
    print(f"{'='*60}")
    print(name_resp)

    # Confirm name
    await send(writer, "Y")

    # Wait for "New character" + password prompt
    new_char_resp = await read_until(reader, "密码", timeout=5.0)
    print(f"\n{'='*60}")
    print("[4] NEW CHARACTER + PASSWORD PROMPT")
    print(f"{'='*60}")
    print(new_char_resp)

    # Send password
    await send(writer, PASSWORD)

    # Wait for retype prompt
    pwd_resp = await read_until(reader, "密码", timeout=5.0)
    print(f"\n{'='*60}")
    print("[5] PASSWORD CONFIRM")
    print(f"{'='*60}")
    print(pwd_resp)

    # Retype password
    await send(writer, PASSWORD)

    # Wait for race prompt
    race_resp = await read_until(reader, "race", timeout=8.0)
    print(f"\n{'='*60}")
    print("[6] RACE PROMPT")
    print(f"{'='*60}")
    print(race_resp)

    # Select race
    await send(writer, "human")

    # Wait for sex prompt
    sex_resp = await read_until(reader, "sex", timeout=5.0)
    print(f"\n{'='*60}")
    print("[7] SEX PROMPT")
    print(f"{'='*60}")
    print(sex_resp)

    # Select sex
    await send(writer, "M")

    # Wait for class prompt
    class_resp = await read_until(reader, "class", timeout=5.0)
    print(f"\n{'='*60}")
    print("[8] CLASS PROMPT")
    print(f"{'='*60}")
    print(class_resp)

    # Select class
    await send(writer, "warrior")

    # Wait for alignment prompt
    align_resp = await read_until(reader, "alignment", timeout=5.0)
    print(f"\n{'='*60}")
    print("[9] ALIGNMENT PROMPT")
    print(f"{'='*60}")
    print(align_resp)

    # Select alignment
    await send(writer, "N")

    # Wait for customize prompt
    custom_resp = await read_until(reader, "customize", timeout=5.0)
    print(f"\n{'='*60}")
    print("[10] CUSTOMIZE PROMPT")
    print(f"{'='*60}")
    print(custom_resp)

    # Skip customization
    await send(writer, "N")

    # Wait for weapon prompt
    weapon_resp = await read_until(reader, "choice", timeout=5.0)
    print(f"\n{'='*60}")
    print("[11] WEAPON PROMPT")
    print(f"{'='*60}")
    print(weapon_resp)

    # Select weapon
    await send(writer, "sword")

    # Wait for MOTD / Hit Return
    motd_resp = await read_until(reader, "return", timeout=10.0)
    print(f"\n{'='*60}")
    print("[12] MOTD")
    print(f"{'='*60}")
    print(motd_resp[:2000])

    # Press Enter to continue
    await send(writer, "")

    # Wait for game to load + look auto
    game_resp = await read_all(reader, timeout=5.0)
    print(f"\n{'='*60}")
    print("[13] ENTERING GAME (look auto)")
    print(f"{'='*60}")
    print(game_resp[:3000])

    # Now run test commands
    commands = [
        "look",
        "score",
        "config",
        "affects",
        "equipment",
        "inventory",
        "help help",
    ]
    results = {}
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"CMD: {cmd}")
        print(f"{'='*60}")
        await send(writer, cmd)
        await asyncio.sleep(1.5)
        output = await read_all(reader, timeout=3.0)
        results[cmd] = output
        print(output[:3000])

    # Quit
    print(f"\n{'='*60}")
    print("QUIT")
    print(f"{'='*60}")
    await send(writer, "quit")
    await asyncio.sleep(1.0)
    quit_resp = await read_all(reader, timeout=2.0)
    print(quit_resp)

    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass

    # Analysis
    print(f"\n\n{'='*60}")
    print("i18n ANALYSIS SUMMARY")
    print(f"{'='*60}")
    chinese_re = re.compile(r"[\u4e00-\u9fff]")
    issues = []
    for cmd, output in results.items():
        has_chinese = bool(chinese_re.search(output))
        cn_count = len(chinese_re.findall(output))
        total_len = len(output.strip())
        status = "OK" if has_chinese else "MISSING"
        print(f"  [{cmd:12s}] {status} - Chinese chars: {cn_count}, total: {total_len}")
        if not has_chinese and total_len > 10:
            issues.append(cmd)
            print(f"    FIRST 300: {output[:300]}")

    if issues:
        print(f"\nWARNING: Commands without Chinese output: {issues}")
    else:
        print(f"\nAll commands produced Chinese output!")


if __name__ == "__main__":
    asyncio.run(main())
