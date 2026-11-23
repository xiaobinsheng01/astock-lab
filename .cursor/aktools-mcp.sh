#!/bin/sh
# 云端启动会把 mcp.json 的 args 用顿号粘成一个参数，uvx 因此直接退出。
# 三个参数写在这里，配置文件不再带 args。
if command -v uvx >/dev/null 2>&1; then
  UVX=$(command -v uvx)
elif [ -x "$HOME/.local/bin/uvx" ]; then
  UVX=$HOME/.local/bin/uvx
else
  echo "uvx 不在 PATH 里" >&2
  exit 127
fi
exec "$UVX" --from aktools aktools-mcp
