#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
for dependency in python3 curl xdg-open systemctl install; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        printf 'Thiếu lệnh bắt buộc: %s\n' "$dependency" >&2
        exit 1
    fi
done
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit('Cần Python 3.9 trở lên.')
from zoneinfo import ZoneInfo
ZoneInfo('Asia/Bangkok')
PY
systemctl --user show-environment >/dev/null

bin_dir="$HOME/.local/bin"
service_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p -- "$bin_dir" "$service_dir"
install -m 755 -- "$repo_dir/codexusage" "$bin_dir/codexusage"
python3 - "$repo_dir" "$service_dir" "$(command -v python3)" <<'PY'
from pathlib import Path
import sys

repo, destination, python = sys.argv[1:]
def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
template = (Path(repo) / 'codex-usage-dashboard.service').read_text()
unit = template.replace('@PYTHON@', quote(python)).replace('@SERVER@', quote(str(Path(repo) / 'server.py')))
(Path(destination) / 'codex-usage-dashboard.service').write_text(unit)
PY

# Keep variables literal so each shell expands its own HOME and PATH at startup.
# shellcheck disable=SC2016
path_line='export PATH="$HOME/.local/bin:$PATH"'
profiles=("$HOME/.profile" "$HOME/.bashrc")
if [[ ${SHELL:-} == */zsh || -f "$HOME/.zshrc" ]]; then
    profiles+=("$HOME/.zshrc")
fi
for profile in "${profiles[@]}"; do
    if ! grep -Fqx -- "$path_line" "$profile" 2>/dev/null; then
        printf '\n# Codex usage dashboard\n%s\n' "$path_line" >> "$profile"
    fi
done

systemctl --user daemon-reload
systemctl --user enable codex-usage-dashboard.service
systemctl --user restart codex-usage-dashboard.service
systemctl --user is-active --quiet codex-usage-dashboard.service
printf 'Đã cài codexusage. Mở terminal mới rồi chạy: codexusage\n'
printf 'Chạy ngay trong terminal này: ~/.local/bin/codexusage\n'
printf 'Giữ repo tại: %s\n' "$repo_dir"
