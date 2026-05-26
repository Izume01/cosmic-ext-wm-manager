#!/bin/bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   cosmic-session-manager Installer${NC}"
echo -e "${BLUE}===============================================${NC}"

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

if ! command -v cargo &> /dev/null; then
    echo -e "${YELLOW}⚠ Cargo (Rust) not found. Building cos-cli requires Rust.${NC}"
    
    SHOULD_INSTALL=false
    if [ "$AUTO_YES" = true ]; then
        SHOULD_INSTALL=true
    elif [ -t 0 ]; then
        read -p "Would you like to automatically download and install Rust (rustup)? [Y/n]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            SHOULD_INSTALL=true
        fi
    fi

    if [ "$SHOULD_INSTALL" = true ]; then
        echo -e "${BLUE}Downloading rustup installer...${NC}"
        DOWNLOADER=""
        if command -v curl &> /dev/null; then
            DOWNLOADER="curl"
        elif command -v wget &> /dev/null; then
            DOWNLOADER="wget"
        fi

        if [ -z "$DOWNLOADER" ]; then
            echo -e "${RED}✘ Error: Neither curl nor wget was found. Cannot download Rust installer.${NC}"
            echo -e "Please install curl or wget, or install Rust manually: https://rustup.rs/${NC}"
        else
            # Create a secure temporary script in the workspace rather than piping directly to bash
            TEMP_RUSTUP_SH="./.rustup_install.sh"
            echo -e "${BLUE}Downloading installer script using $DOWNLOADER...${NC}"
            
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
                echo -e "${BLUE}Running rustup installation...${NC}"
                if "$TEMP_RUSTUP_SH" -y; then
                    echo -e "${GREEN}✔ Rust successfully installed!${NC}"
                    if [ -f "$HOME/.cargo/env" ]; then
                        source "$HOME/.cargo/env"
                    fi
                else
                    echo -e "${RED}✘ Rust installation failed.${NC}"
                fi
                rm -f "$TEMP_RUSTUP_SH"
            else
                echo -e "${RED}✘ Failed to download the Rust installer script.${NC}"
                rm -f "$TEMP_RUSTUP_SH"
            fi
        fi
    else
        echo -e "${YELLOW}⚠ Skipping Rust installation. Building cos-cli will be skipped.${NC}"
    fi
fi

if command -v cargo &> /dev/null; then
    echo -e "${GREEN}✔ Cargo detected.${NC}"
    if [ ! -f "$HOME/.cargo/bin/cos-cli" ]; then
        echo -e "${BLUE}Installing Wayland native helper (cos-cli)...${NC}"
        if cargo install --git https://github.com/estin/cos-cli; then
            echo -e "${GREEN}✔ Native helper cos-cli successfully installed!${NC}"
        else
            echo -e "${RED}✘ Failed to install cos-cli via cargo. Skipping...${NC}"
        fi
    else
        echo -e "${GREEN}✔ Native helper cos-cli already installed at ~/.cargo/bin/cos-cli${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Skipping building cos-cli since Cargo is not available.${NC}"
fi


echo -e "${BLUE}Creating Python Virtual Environment...${NC}"
python3 -m venv .venv

echo -e "${BLUE}Installing Python dependencies...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

echo -e "${BLUE}Creating global shortcut launcher: ${LOCAL_BIN}/cosmic-wm...${NC}"
cat << EOF > "$LOCAL_BIN/cosmic-wm"
#!/bin/bash
exec "$(pwd)/.venv/bin/cosmic-wm" "\$@"
EOF
chmod +x "$LOCAL_BIN/cosmic-wm"

mkdir -p "$HOME/.config/cosmic-wm-manager/profiles"
mkdir -p "$HOME/.config/cosmic-wm-manager/sessions"

cp profiles/dev.yaml "$HOME/.config/cosmic-wm-manager/profiles/dev.yaml"

echo -e "${BLUE}===============================================${NC}"
echo -e "${GREEN}✔ Installation completed successfully!${NC}"
echo -e "${GREEN}  You can now run '${BLUE}cosmic-wm --help${GREEN}'${NC}"
echo -e "${GREEN}  Make sure '${BLUE}${LOCAL_BIN}${GREEN}' is in your \$PATH.${NC}"
echo -e "${BLUE}===============================================${NC}"
