#!/bin/bash
set -e

# Style Definitions
BOLD='\033[1m'
DIM='\033[2m'

# Foreground Colors
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
MAGENTA='\033[35m'
CYAN='\033[36m'
WHITE='\033[37m'

# Bold Colors
B_RED='\033[1;31m'
B_GREEN='\033[1;32m'
B_YELLOW='\033[1;33m'
B_BLUE='\033[1;34m'
B_MAGENTA='\033[1;35m'
B_CYAN='\033[1;36m'
B_WHITE='\033[1;37m'

# Reset Color
NC='\033[0m'

# Print Vercel-style clean header
echo -e "${B_WHITE}▲ cosmic-session-manager${NC} ${DIM}installer${NC}"
echo

AUTO_YES=false
for arg in "$@"; do
    if [ "$arg" = "-y" ] || [ "$arg" = "--yes" ]; then
        AUTO_YES=true
    fi
done

# Try sourcing cargo environment if Rust was installed but isn't in current path
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

# ===================================================
# STEP 1: RUST TOOLCHAIN
# ===================================================
if ! command -v cargo &> /dev/null; then
    echo -e "${B_YELLOW}⚠${NC} Cargo (Rust) not found. Building the native helper requires Rust."
    
    SHOULD_INSTALL=false
    if [ "$AUTO_YES" = true ]; then
        SHOULD_INSTALL=true
    elif [ -t 0 ]; then
        read -p "  👉 Would you like to automatically download and install Rust (rustup)? [Y/n]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            SHOULD_INSTALL=true
        fi
    fi

    if [ "$SHOULD_INSTALL" = true ]; then
        echo -e "${DIM}• Downloading rustup installer...${NC}"
        DOWNLOADER=""
        if command -v curl &> /dev/null; then
            DOWNLOADER="curl"
        elif command -v wget &> /dev/null; then
            DOWNLOADER="wget"
        fi

        if [ -z "$DOWNLOADER" ]; then
            echo -e "${B_RED}✗${NC} Error: Neither curl nor wget was found. Cannot download Rust installer."
            echo -e "  Please install curl or wget, or install Rust manually: https://rustup.rs/"
        else
            TEMP_RUSTUP_SH="./.rustup_install.sh"
            echo -e "${DIM}• Downloading installer script using $DOWNLOADER...${NC}"
            
            DOWNLOAD_SUCCESS=false
            if [ "$DOWNLOADER" = "curl" ]; then
                if curl --proto '=https' --tlsv1.2 -sSfL https://sh.rustup.rs -o "$TEMP_RUSTUP_SH"; then
                    DOWNLOAD_SUCCESS=true
                fi
            elif [ "$DOWNLOADER" = "wget" ]; then
                if wget --https-only --secure-protocol=TLSv1_2 -qO "$TEMP_RUSTUP_SH" https://sh.rustup.rs; then
                    DOWNLOAD_SUCCESS=true
                fi
            fi

            if [ "$DOWNLOAD_SUCCESS" = true ]; then
                chmod +x "$TEMP_RUSTUP_SH"
                echo -e "${DIM}• Running rustup installation...${NC}"
                if "$TEMP_RUSTUP_SH" -y; then
                    echo -e "${B_GREEN}✓${NC} Rust successfully installed!"
                    if [ -f "$HOME/.cargo/env" ]; then
                        source "$HOME/.cargo/env"
                    fi
                else
                    echo -e "${B_RED}✗${NC} Rust installation failed."
                fi
                rm -f "$TEMP_RUSTUP_SH"
            else
                echo -e "${B_RED}✗${NC} Failed to download the Rust installer script."
                rm -f "$TEMP_RUSTUP_SH"
            fi
        fi
    else
        echo -e "${B_YELLOW}⚠${NC} Skipping Rust installation. Building cos-cli will be skipped."
    fi
else
    echo -e "${B_GREEN}✓${NC} Cargo environment detected: ${DIM}$(cargo --version)${NC}"
fi

# ===================================================
# STEP 2: NATIVE HELPER
# ===================================================
if command -v cargo &> /dev/null; then
    if [ ! -f "$HOME/.cargo/bin/cos-cli" ]; then
        echo -e "${DIM}• Building and installing Wayland helper from git...${NC}"
        if cargo install --git https://github.com/estin/cos-cli; then
            echo -e "${B_GREEN}✓${NC} Native helper cos-cli successfully compiled and installed!"
        else
            echo -e "${B_RED}✗${NC} Failed to install cos-cli via cargo. Skipping compilation..."
        fi
    else
        echo -e "${B_GREEN}✓${NC} Native helper cos-cli is up to date"
    fi
else
    echo -e "${B_YELLOW}⚠${NC} Skipping building cos-cli since Cargo is not available."
fi

# ===================================================
# STEP 3: PYTHON VIRTUAL ENVIRONMENT
# ===================================================
python3 -m venv .venv
echo -e "${B_GREEN}✓${NC} Python virtual environment created"

echo -e "${DIM}• Upgrading pip and installing package dependencies...${NC}"
.venv/bin/pip install --upgrade pip > /dev/null 2>&1 || true
.venv/bin/pip install -e . > /dev/null 2>&1
echo -e "${B_GREEN}✓${NC} Package dependencies and libraries installed successfully"

# ===================================================
# STEP 4: ENTRYPOINTS & PATHS
# ===================================================
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

cat << EOF > "$LOCAL_BIN/cosmic-wm"
#!/bin/bash
exec "$(pwd)/.venv/bin/cosmic-wm" "\$@"
EOF
chmod +x "$LOCAL_BIN/cosmic-wm"
echo -e "${B_GREEN}✓${NC} Global launcher shortcut written to ${LOCAL_BIN}/cosmic-wm"

mkdir -p "$HOME/.config/cosmic-wm-manager/profiles"
mkdir -p "$HOME/.config/cosmic-wm-manager/sessions"
cp profiles/dev.yaml "$HOME/.config/cosmic-wm-manager/profiles/dev.yaml"
echo -e "${B_GREEN}✓${NC} Default configuration profiles copied"

echo
# Final Vercel success layout
echo -e "${B_GREEN}Success!${NC} cosmic-session-manager is ready to use."
echo -e "${DIM}•${NC} Command:  ${B_CYAN}cosmic-wm --help${NC}"
echo -e "${DIM}•${NC} Bin path: ${BLUE}${LOCAL_BIN}${NC}"
echo
