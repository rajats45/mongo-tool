#!/bin/bash

# This script must be run as root (e.g., with sudo)
if [ "$EUID" -ne 0 ]; then 
  echo "Please run this installer with sudo:"
  echo "curl ... | sudo bash"
  exit 1
fi

# --- Configuration ---
# !! CHANGE THIS LINE to your GitHub repo's URL !!
REPO_URL="https://github.com/rajats45/mongo-tool.git"

# Get the non-sudo user who ran the command
REAL_USER="${SUDO_USER:-$(whoami)}"

# Install directory
INSTALL_DIR="/opt/mongo-tool"

echo "--- Starting MongoDB Tool Installer ---"

# 1. Install Dependencies
echo "[1/5] Installing dependencies (git, python3-pip, ufw, docker)..."
apt-get update > /dev/null
apt-get install -y git python3-pip ufw ca-certificates curl > /dev/null

# Install Docker (if not already present)
if ! command -v docker &> /dev/null; then
    echo "   > Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update > /dev/null
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null
    systemctl enable --now docker > /dev/null
    usermod -aG docker "$REAL_USER"
    echo "   > Docker installed."
fi

pip install Flask > /dev/null

# 2. Clone the Repository
echo "[2/5] Cloning project from GitHub..."
if [ -d "$INSTALL_DIR" ]; then
    echo "   > Found existing directory. Pulling updates..."
    (cd "$INSTALL_DIR" && git pull)
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
chown -R "$REAL_USER":"$REAL_USER" "$INSTALL_DIR"

# 3. Set up UFW Permission
echo "[3/5] Setting up Sudo permissions for UFW..."
# Create a new file in /etc/sudoers.d/
echo "$REAL_USER ALL=(ALL) NOPASSWD: /usr/sbin/ufw" > /etc/sudoers.d/90-mongo-tool
chmod 0440 /etc/sudoers.d/90-mongo-tool
echo "   > UFW is now controllable by the app."

# 4. Create the 'mongo-tool' command
echo "[4/5] Creating 'mongo-tool' command..."

# Create a small script to start the server
cat << EOF > "$INSTALL_DIR/start.sh"
#!/bin/bash
echo "Starting MongoDB Manager..."
echo "Access the GUI at: http://$(hostname -I | awk '{print $1}'):5000"
echo "Press Ctrl+C to stop the server."

# Add user to docker group in this session if not already
if ! groups $USER | grep &>/dev/null '\\bdocker\\b'; then
    sudo usermod -aG docker $USER
    echo "You've been added to the 'docker' group. Please log out and log back in, then run 'mongo-tool' again."
    exit 1
fi

cd "$INSTALL_DIR"
python3 app.py
EOF

chmod +x "$INSTALL_DIR/start.sh"

# Symlink it to /usr/local/bin to make it a global command
if [ -f "/usr/local/bin/mongo-tool" ]; then
    rm "/usr/local/bin/mongo-tool"
fi
ln -s "$INSTALL_DIR/start.sh" /usr/local/bin/mongo-tool

# 5. Final Instructions
echo "[5/5] Installation Complete!"
echo ""
echo "--- To Use Your Tool ---"
echo "1. IMPORTANT: Edit your password in: $INSTALL_DIR/docker-compose.yml"
echo "2. ALSO IMPORTANT: Edit the password in: $INSTALL_DIR/app.py (in the backup() function)"
echo "3. Run the tool by simply typing:"
echo ""
echo "   mongo-tool"
echo ""
echo "(If you get a docker 'permission denied' error, please log out and log back in, then run 'mongo-tool' again.)"