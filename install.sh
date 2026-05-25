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

if ! command -v cargo &> /dev/null; then
    echo -e "${YELLOW}⚠ Cargo (Rust) not found. Building cos-cli will be skipped.${NC}"
    echo -e "${YELLOW}Please install Rust using: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh${NC}"
else
    echo -e "${GREEN}✔ Cargo detected.${NC}"
    if [ ! -f "$HOME/.cargo/bin/cos-cli" ]; then
        echo -e "${BLUE}Installing Wayland native helper (cos-cli)...${NC}"
        cargo install --git https://github.com/estin/cos-cli
    else
        echo -e "${GREEN}✔ Native helper cos-cli already installed at ~/.cargo/bin/cos-cli${NC}"
    fi
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
