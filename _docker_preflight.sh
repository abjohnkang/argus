# shellcheck shell=bash
# Shared Docker pre-flight for Argus entry scripts (run_server.sh, run_debug.sh).
#
# Source-only; do NOT execute directly. Both entry scripts source this file
# and then call `ensure_docker_ready`.
#
# Policy (chosen 2026-06-04):
#   - Auto-START Docker if installed but daemon is unreachable.
#   - Auto-INSTALL is NOT performed — print platform-specific install
#     command and exit 1 instead. Auto-install requires sudo / admin
#     credentials / multi-GB downloads / kernel extensions; doing it
#     silently is a "surprise package install" red flag for a privacy-
#     individual project. The user stays in control of installation.
#
# Supported runtimes (auto-start best-effort, in order of preference):
#   macOS:         Docker Desktop -> Colima -> OrbStack
#   Linux-systemd: `sudo systemctl start docker`
#   WSL:           No auto-start (daemon is on the Windows host); instruct.
#   Other:         Detect+instruct only.
#
# Config:
#   ARGUS_DOCKER_WAIT — seconds to wait for daemon ready after start (default 60)

# Detect platform: prints one of {macos, linux-systemd, linux-other, wsl, unknown}
_docker_preflight_detect_platform() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null \
        || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
        echo "wsl"
      elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        echo "linux-systemd"
      else
        echo "linux-other"
      fi
      ;;
    *) echo "unknown" ;;
  esac
}

# Print platform-specific install instructions to stderr.
_docker_preflight_print_install() {
  local platform="$1"
  echo "ERROR: Docker CLI not found on PATH. Argus requires Docker Engine + Compose v2." >&2
  echo "" >&2
  case "$platform" in
    macos)
      echo "Install Docker Desktop (recommended for most users):" >&2
      echo "  brew install --cask docker" >&2
      echo "  open -a Docker   # accept the license, then it stays running" >&2
      echo "" >&2
      echo "Lightweight alternatives (also auto-detected by this script):" >&2
      echo "  brew install colima              # daemon-only, no Desktop UI" >&2
      echo "  brew install --cask orbstack     # fast native macOS alternative" >&2
      ;;
    linux-systemd)
      if command -v apt-get >/dev/null 2>&1; then
        echo "Install Docker Engine (Debian/Ubuntu):" >&2
        echo "  sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin" >&2
        echo "  sudo systemctl enable --now docker" >&2
        # shellcheck disable=SC2016
        echo '  sudo usermod -aG docker $USER    # then log out and back in' >&2
      elif command -v dnf >/dev/null 2>&1; then
        echo "Install Docker Engine (Fedora/RHEL):" >&2
        echo "  sudo dnf install -y docker docker-compose-plugin" >&2
        echo "  sudo systemctl enable --now docker" >&2
        # shellcheck disable=SC2016
        echo '  sudo usermod -aG docker $USER' >&2
      elif command -v pacman >/dev/null 2>&1; then
        echo "Install Docker Engine (Arch):" >&2
        echo "  sudo pacman -S docker docker-compose" >&2
        echo "  sudo systemctl enable --now docker" >&2
        # shellcheck disable=SC2016
        echo '  sudo usermod -aG docker $USER' >&2
      else
        echo "Install Docker via your distribution's package manager, then:" >&2
        echo "  sudo systemctl enable --now docker" >&2
      fi
      ;;
    linux-other)
      echo "Install Docker Engine via your distribution's package manager." >&2
      echo "Without systemd: 'sudo service docker start' or your init system's equivalent." >&2
      ;;
    wsl)
      echo "Install Docker Desktop on the Windows host:" >&2
      echo "  winget install Docker.DockerDesktop" >&2
      echo "Then enable WSL integration: Docker Desktop > Settings > Resources > WSL Integration." >&2
      ;;
    *)
      echo "Install Docker Engine from https://docs.docker.com/engine/install/" >&2
      ;;
  esac
  echo "" >&2
}

# Attempt to start the Docker daemon for the detected platform.
# Returns 0 if a start command was issued, 1 if no auto-start path exists.
_docker_preflight_start() {
  local platform="$1"
  case "$platform" in
    macos)
      if [ -d "/Applications/Docker.app" ]; then
        echo "  Launching Docker Desktop..." >&2
        open -a Docker && return 0
      elif command -v colima >/dev/null 2>&1; then
        echo "  Starting Colima..." >&2
        colima start && return 0
      elif [ -d "/Applications/OrbStack.app" ]; then
        echo "  Launching OrbStack..." >&2
        open -a OrbStack && return 0
      fi
      echo "  No known Docker runtime app found in /Applications and no 'colima' on PATH." >&2
      return 1
      ;;
    linux-systemd)
      echo "  sudo systemctl start docker (may prompt for password)..." >&2
      sudo systemctl start docker && return 0
      echo "  systemctl start docker failed; check 'systemctl status docker' for details." >&2
      return 1
      ;;
    wsl)
      echo "  Docker daemon runs on the Windows host — cannot auto-start from WSL." >&2
      echo "  Start Docker Desktop on Windows and enable WSL integration." >&2
      return 1
      ;;
    *)
      echo "  No auto-start path for platform '$platform'." >&2
      return 1
      ;;
  esac
}

# Poll `docker info` until ready or timeout. Default 60s; ARGUS_DOCKER_WAIT overrides.
_docker_preflight_wait_ready() {
  local timeout="${ARGUS_DOCKER_WAIT:-60}"
  local elapsed=0
  printf "  Waiting for Docker daemon (timeout %ss)" "$timeout" >&2
  while [ "$elapsed" -lt "$timeout" ]; do
    if docker info >/dev/null 2>&1; then
      printf " ready (%ss).\n" "$elapsed" >&2
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    printf "." >&2
  done
  printf " timeout.\n" >&2
  return 1
}

# Public entry point. Called by run_server.sh / run_debug.sh.
# Exits 1 with a clear message on failure; returns 0 on success.
ensure_docker_ready() {
  local platform
  platform="$(_docker_preflight_detect_platform)"

  if ! command -v docker >/dev/null 2>&1; then
    _docker_preflight_print_install "$platform"
    exit 1
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Docker daemon is not reachable; attempting auto-start (platform: $platform)..." >&2
  if ! _docker_preflight_start "$platform"; then
    echo "" >&2
    echo "Could not auto-start Docker. Start it manually and re-run this script." >&2
    exit 1
  fi

  if ! _docker_preflight_wait_ready; then
    echo "" >&2
    echo "Docker did not become ready within \${ARGUS_DOCKER_WAIT:-60}s." >&2
    echo "Check the Docker app / daemon logs and re-run." >&2
    exit 1
  fi
}
