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

# Print Header Banner
echo -e "${B_CYAN}╭───────────────────────────────────────────────────╮${NC}"
echo -e "${B_CYAN}│${NC}  ${B_MAGENTA}🌌 COSMIC Session Manager${NC} ${B_CYAN}─${NC} ${WHITE}Installation Wizard${NC}  ${B_CYAN}│${NC}"
echo -e "${B_CYAN}╰───────────────────────────────────────────────────╯${NC}"
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
echo -e "${B_BLUE}[ 🚀 Step 1/4 ]${NC} ${BOLD}Checking Rust Toolchain Environment...${NC}"

if ! command -v cargo &> /dev/null; then
    echo -e "         ${B_YELLOW}⚠️ Cargo (Rust) not found. Building the native helper requires Rust.${NC}"
    
    SHOULD_INSTALL=false
    if [ "$AUTO_YES" = true ]; then
        SHOULD_INSTALL=true
    elif [ -t 0 ]; then
        read -p "         👉 Would you like to automatically download and install Rust (rustup)? [Y/n]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            SHOULD_INSTALL=true
        fi
    fi

    if [ "$SHOULD_INSTALL" = true ]; then
        echo -e "         ${B_BLUE}⏳ Downloading rustup installer...${NC}"
        DOWNLOADER=""
        if command -v curl &> /dev/null; then
            DOWNLOADER="curl"
        elif command -v wget &> /dev/null; then
            DOWNLOADER="wget"
        fi

        if [ -z "$DOWNLOADER" ]; then
            echo -e "         ${B_RED}❌ Error: Neither curl nor wget was found. Cannot download Rust installer.${NC}"
            echo -e "         Please install curl or wget, or install Rust manually: https://rustup.rs/${NC}"
        else
            # Create a secure temporary script in the workspace rather than piping directly to bash
            TEMP_RUSTUP_SH="./.rustup_install.sh"
            echo -e "         ${B_BLUE}⏳ Downloading installer script using $DOWNLOADER...${NC}"
            
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
                echo -e "         ${B_BLUE}⚙️  Running rustup installation...${NC}"
                if "$TEMP_RUSTUP_SH" -y; then
                    echo -e "         ${B_GREEN}✨ Rust successfully installed!${NC}"
                    if [ -f "$HOME/.cargo/env" ]; then
                        source "$HOME/.cargo/env"
                    fi
                else
                    echo -e "         ${B_RED}❌ Rust installation failed.${NC}"
                fi
                rm -f "$TEMP_RUSTUP_SH"
            else
                echo -e "         ${B_RED}❌ Failed to download the Rust installer script.${NC}"
                rm -f "$TEMP_RUSTUP_SH"
            fi
        fi
    else
        echo -e "         ${B_YELLOW}⚠️ Skipping Rust installation. Building cos-cli will be skipped.${NC}"
    fi
else
    echo -e "         ${B_GREEN}✔ Cargo detected:${NC} ${DIM}$(cargo --version)${NC}"
fi
echo

# ===================================================
# STEP 2: NATIVE HELPER
# ===================================================
echo -e "${B_BLUE}[ 📦 Step 2/4 ]${NC} ${BOLD}Installing Wayland Native Helper (cos-cli)...${NC}"

if command -v cargo &> /dev/null; then
    if [ ! -f "$HOME/.cargo/bin/cos-cli" ]; then
        echo -e "         ${B_BLUE}⏳ Building and installing Wayland helper from git...${NC}"
        if cargo install --git https://github.com/estin/cos-cli; then
            echo -e "         ${B_GREEN}✨ Native helper cos-cli successfully compiled and installed!${NC}"
        else
            echo -e "         ${B_RED}❌ Failed to install cos-cli via cargo. Skipping compilation...${NC}"
        fi
    else
        echo -e "         ${B_GREEN}✔ Native helper cos-cli already installed at ~/.cargo/bin/cos-cli${NC}"
    fi
else
    echo -e "         ${B_YELLOW}⚠️ Skipping building cos-cli since Cargo is not available.${NC}"
fi
echo

# ===================================================
# STEP 3: PYTHON VIRTUAL ENVIRONMENT
# ===================================================
echo -e "${B_BLUE}[ 🐍 Step 3/4 ]${NC} ${BOLD}Setting up Python Virtual Environment...${NC}"
echo -e "         ${B_BLUE}⏳ Creating dedicated virtual environment (.venv)...${NC}"
python3 -m venv .venv

echo -e "         ${B_BLUE}⏳ Upgrading pip and installing dependencies in editable mode...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
echo -e "         ${B_GREEN}✔ Python dependencies and package successfully installed!${NC}"
echo

# ===================================================
# STEP 4: ENTRYPOINTS & PATHS
# ===================================================
echo -e "${B_BLUE}[ ⚙️  Step 4/4 ]${NC} ${BOLD}Configuring Application Entrypoints...${NC}"

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

echo -e "         ${B_BLUE}⏳ Writing global shortcut launcher to ${LOCAL_BIN}/cosmic-wm...${NC}"
cat << EOF > "$LOCAL_BIN/cosmic-wm"
#!/bin/bash
exec "$(pwd)/.venv/bin/cosmic-wm" "\$@"
EOF
chmod +x "$LOCAL_BIN/cosmic-wm"

echo -e "         ${B_BLUE}⏳ Creating user configuration directories...${NC}"
mkdir -p "$HOME/.config/cosmic-wm-manager/profiles"
mkdir -p "$HOME/.config/cosmic-wm-manager/sessions"

echo -e "         ${B_BLUE}⏳ Copying default development profile...${NC}"
cp profiles/dev.yaml "$HOME/.config/cosmic-wm-manager/profiles/dev.yaml"

echo -e "         ${B_GREEN}✔ Workspace environment configured successfully!${NC}"
echo

# Final Success Banner
echo
echo -e "${B_GREEN}╭───────────────────────────────────────────────────╮${NC}"
echo -e "${B_GREEN}│${NC}         ${B_GREEN}✨ INSTALLATION COMPLETED SUCCESSFULLY! ✨${NC}        ${B_GREEN}│${NC}"
echo -e "${B_GREEN}├───────────────────────────────────────────────────┤${NC}"
echo -e "${B_GREEN}│${NC}  ${BOLD}You can now run:${NC}  ${B_CYAN}cosmic-wm --help${NC}                   ${B_GREEN}│${NC}"
echo -e "${B_GREEN}│${NC}                                                   ${B_GREEN}│${NC}"
echo -e "${B_GREEN}│${NC}  ${BOLD}Note:${NC} Make sure ${B_BLUE}${LOCAL_BIN}${NC} is in your ${B_YELLOW}\$PATH${NC}.     ${B_GREEN}│${NC}"
echo -e "${B_GREEN}╰───────────────────────────────────────────────────╯${NC}"
echo
