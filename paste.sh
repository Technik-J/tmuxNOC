#!/usr/bin/env bash

# This script behaves like `yank.sh`. It will output system clipboard content to stdout, but when
# argument 'tmux' send to it, it will set tmux buffer with system clipboard content. This is
# because I was trying to set tmux buffer with command `run 'tmux set-buffer "$($paste)"'` and for
# the most parts it works, but when used with combination of `send-keys -X cancel`, it doesn't
# work. Hence this workaround.

set -e

is_app_installed() {
  type "$1" &>/dev/null
}

paste_backend=""
if is_app_installed paste.exe; then
  paste_backend="paste.exe"
fi

if [ -n "$paste_backend" ]; then
  if [ "$1" = "tmux" ]; then
    tmux set-buffer "$($paste_backend)"
  else
    printf "%s" "$($paste_backend)"
  fi
  exit;
fi