# shellcheck shell=bash
# Shared Docker pre-flight for Argus entry scripts (run_server.sh, run_debug.sh).
#
# Source-only; do NOT execute directly. Both entry scripts source this file
# and then call `ensure_docker_ready`.
#
# Policy (revised 2026-06-04, see CHANGELOG.md):
#   - Auto-START Docker if installed but daemon is unreachable.
#   - FORCE-INSTALL Docker if not installed (on supported platforms).
#       * macOS: prefer `brew install --cask docker`; fall back to direct
#         Docker.dmg download + hdiutil + sudo cp -R to /Applications.
#       * Linux-systemd: `sudo {apt-get|dnf|pacman} install ...` followed
#         by `sudo systemctl enable --now docker`.
#       * Linux-other / WSL: cannot reliably auto-install across these
#         boundaries (no systemd; WSL daemon lives on Windows host) -
#         print platform-specific instructions and exit.
#   - No confirmation prompt: invoking ./run_server.sh or ./run_debug.sh
#     is the consent. OS-level admin / sudo password prompts will still
#     appear naturally during install where required.
#
# Supported runtimes (auto-start best-effort, in order of preference):
#   macOS:         Docker Desktop -> Colima -> OrbStack
#   Linux-systemd: `sudo systemctl start docker`
#   WSL:           No auto-start (daemon is on the Windows host); instruct.
#   Other:         Detect+instruct only.
#
# Config:
#   ARGUS_DOCKER_WAIT          - seconds to wait for daemon ready (default 60)
#   ARGUS_DOCKER_WAIT_INSTALL  - seconds to wait after a fresh install
#                                (default 180; Docker Desktop first-launch
#                                may need license / kernel-ext acceptance)

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

# Print platform-specific install instructions to stderr (fallback path only).
_docker_preflight_print_install() {
  local platform="$1"
  echo "ERROR: Argus could not auto-install Docker on platform '$platform'." >&2
  echo "Install Docker Engine + Compose v2 manually, then re-run this script." >&2
  echo "" >&2
  case "$platform" in
    macos)
      echo "macOS:" >&2
      echo "  brew install --cask docker" >&2
      echo "  open -a Docker   # accept the license, then it stays running" >&2
      echo "" >&2
      echo "Or download Docker.dmg from https://www.docker.com/products/docker-desktop/" >&2
      ;;
    linux-systemd)
      echo "Linux (systemd):" >&2
      if command -v apt-get >/dev/null 2>&1; then
        echo "  sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin" >&2
      elif command -v dnf >/dev/null 2>&1; then
        echo "  sudo dnf install -y docker docker-compose-plugin" >&2
      elif command -v pacman >/dev/null 2>&1; then
        echo "  sudo pacman -S docker docker-compose" >&2
      else
        echo "  Use your distribution's package manager to install docker." >&2
      fi
      echo "  sudo systemctl enable --now docker" >&2
      # shellcheck disable=SC2016
      echo '  sudo usermod -aG docker $USER  # then log out and back in' >&2
      ;;
    linux-other)
      echo "Linux (non-systemd):" >&2
      echo "  Install docker via your distribution's package manager," >&2
      echo "  then start via 'sudo service docker start' or your init system's equivalent." >&2
      ;;
    wsl)
      echo "WSL: Docker Desktop must be installed on the Windows HOST (not in WSL):" >&2
      echo "  Run on Windows PowerShell as Administrator:" >&2
      echo "    winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements" >&2
      echo "  Then enable WSL integration: Docker Desktop > Settings > Resources > WSL Integration" >&2
      ;;
    *)
      echo "See https://docs.docker.com/engine/install/" >&2
      ;;
  esac
  echo "" >&2
}

# macOS install via brew (preferred when brew is available).
_docker_preflight_install_macos_brew() {
  echo "  brew install --cask docker (may prompt for admin password)..." >&2
  if ! brew install --cask docker; then
    echo "  brew install failed." >&2
    return 1
  fi
  echo "  brew install succeeded; launching Docker Desktop..." >&2
  open -a Docker
  return 0
}

# macOS install via direct DMG download (when brew is not present).
_docker_preflight_install_macos_dmg() {
  local arch dmg_url tmpdmg mountpoint
  arch="$(uname -m)"
  case "$arch" in
    arm64)  dmg_url="https://desktop.docker.com/mac/main/arm64/Docker.dmg" ;;
    x86_64) dmg_url="https://desktop.docker.com/mac/main/amd64/Docker.dmg" ;;
    *) echo "  Unsupported macOS architecture: $arch" >&2; return 1 ;;
  esac

  tmpdmg="$(mktemp -t Docker)" || return 1
  mv "$tmpdmg" "${tmpdmg}.dmg"
  tmpdmg="${tmpdmg}.dmg"

  echo "  Downloading Docker.dmg for $arch from desktop.docker.com (~600 MB)..." >&2
  if ! curl -fL --progress-bar -o "$tmpdmg" "$dmg_url"; then
    echo "  Download failed." >&2
    rm -f "$tmpdmg"
    return 1
  fi

  echo "  Mounting DMG..." >&2
  mountpoint="$(hdiutil attach -nobrowse -noautoopen -quiet "$tmpdmg" \
                | awk -F'\t' '/\/Volumes\// {print $NF; exit}')"
  if [ -z "$mountpoint" ] || [ ! -d "$mountpoint/Docker.app" ]; then
    echo "  DMG mount or Docker.app discovery failed (mountpoint='$mountpoint')." >&2
    rm -f "$tmpdmg"
    return 1
  fi

  echo "  Copying Docker.app to /Applications (will prompt for admin password)..." >&2
  if ! sudo cp -R "$mountpoint/Docker.app" /Applications/; then
    echo "  sudo cp to /Applications failed." >&2
    hdiutil detach -quiet "$mountpoint" 2>/dev/null || true
    rm -f "$tmpdmg"
    return 1
  fi

  hdiutil detach -quiet "$mountpoint" 2>/dev/null || true
  rm -f "$tmpdmg"

  echo "  Docker Desktop installed; launching..." >&2
  echo "  Note: first launch may require license acceptance and kernel-extension approval." >&2
  open -a Docker
  return 0
}

# Linux (systemd) install via distribution package manager.
_docker_preflight_install_linux_systemd() {
  if ! command -v sudo >/dev/null 2>&1; then
    echo "  ERROR: 'sudo' not found on PATH. Cannot install Docker without sudo." >&2
    return 1
  fi
  if command -v apt-get >/dev/null 2>&1; then
    echo "  sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin (may prompt for password)..." >&2
    sudo apt-get update -qq || return 1
    sudo apt-get install -y docker.io docker-compose-plugin || return 1
  elif command -v dnf >/dev/null 2>&1; then
    echo "  sudo dnf install -y docker docker-compose-plugin (may prompt for password)..." >&2
    sudo dnf install -y docker docker-compose-plugin || return 1
  elif command -v pacman >/dev/null 2>&1; then
    echo "  sudo pacman -S --noconfirm docker docker-compose (may prompt for password)..." >&2
    sudo pacman -S --noconfirm docker docker-compose || return 1
  else
    echo "  No supported package manager (apt-get / dnf / pacman) found." >&2
    return 1
  fi
  echo "  Enabling and starting docker.service..." >&2
  sudo systemctl enable --now docker || return 1
  echo "  Optional (run later, then log out / back in for group change to take effect):" >&2
  # shellcheck disable=SC2016
  echo '    sudo usermod -aG docker $USER' >&2
  return 0
}

# Dispatch to platform-specific install.
_docker_preflight_install() {
  local platform="$1"
  case "$platform" in
    macos)
      if command -v brew >/dev/null 2>&1; then
        _docker_preflight_install_macos_brew
      else
        _docker_preflight_install_macos_dmg
      fi
      ;;
    linux-systemd)
      _docker_preflight_install_linux_systemd
      ;;
    *)
      echo "  Force-install not supported on platform: $platform" >&2
      return 1
      ;;
  esac
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
      echo "  Docker daemon runs on the Windows host - cannot auto-start from WSL." >&2
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
# Pass "install" as $1 to use the longer post-install default (180s).
_docker_preflight_wait_ready() {
  local mode="${1:-normal}"
  local timeout
  if [ "$mode" = "install" ]; then
    timeout="${ARGUS_DOCKER_WAIT_INSTALL:-180}"
  else
    timeout="${ARGUS_DOCKER_WAIT:-60}"
  fi
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

  # Fast path: Docker already installed and daemon already reachable.
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    return 0
  fi

  local did_install=0

  # Step 1: Force-install if Docker is missing.
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found; attempting force-install (platform: $platform)..." >&2
    if ! _docker_preflight_install "$platform"; then
      echo "" >&2
      _docker_preflight_print_install "$platform"
      exit 1
    fi
    did_install=1
    # On macOS, the install path also launches Docker Desktop; fall through to wait.
    # On Linux-systemd, the install path calls `systemctl enable --now docker`; daemon
    # should already be starting; fall through to wait.
  fi

  # Step 2: Auto-start if Docker is installed but daemon is not reachable.
  # Skip if install already kicked off the start (the install paths leave the
  # daemon starting; double-starting is wasteful but not harmful).
  if [ "$did_install" -eq 0 ] && ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not reachable; attempting auto-start (platform: $platform)..." >&2
    if ! _docker_preflight_start "$platform"; then
      echo "" >&2
      echo "Could not auto-start Docker. Start it manually and re-run this script." >&2
      exit 1
    fi
  fi

  # Step 3: Wait for daemon ready. Longer timeout if we just installed.
  local wait_mode="normal"
  if [ "$did_install" -eq 1 ]; then
    wait_mode="install"
  fi
  if ! _docker_preflight_wait_ready "$wait_mode"; then
    echo "" >&2
    if [ "$did_install" -eq 1 ]; then
      echo "Docker did not become ready within \${ARGUS_DOCKER_WAIT_INSTALL:-180}s after install." >&2
      echo "On macOS first launch, Docker Desktop may be waiting for you to accept the" >&2
      echo "license and approve the kernel extension. Open Docker Desktop, complete those" >&2
      echo "prompts, then re-run this script." >&2
    else
      echo "Docker did not become ready within \${ARGUS_DOCKER_WAIT:-60}s." >&2
      echo "Check the Docker app / daemon logs and re-run." >&2
    fi
    exit 1
  fi
}
