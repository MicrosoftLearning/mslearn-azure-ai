#!/bin/bash
# Install required tools - run this script with sudo or as root

set -e

# Detect package manager
if command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
elif command -v yum &>/dev/null; then
    PKG_MANAGER="yum"
else
    echo "Error: No supported package manager found (apt, dnf, yum)."
    exit 1
fi

echo "Using package manager: $PKG_MANAGER"

# ── Python 3.12 ──────────────────────────────────────────────────────────────
echo "Installing Python 3.12..."
if [[ "$PKG_MANAGER" == "apt" ]]; then
    apt-get update -y
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip
elif [[ "$PKG_MANAGER" == "dnf" ]]; then
    dnf install -y python3.12 python3-pip
else
    yum install -y python3.12 python3-pip
fi

# ── PostgreSQL 17 client tools only ──────────────────────────────────────────
echo "Installing PostgreSQL 17 client tools..."
if [[ "$PKG_MANAGER" == "apt" ]]; then
    apt-get install -y curl ca-certificates gnupg
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
    . /etc/os-release
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y
    apt-get install -y postgresql-client-17
elif [[ "$PKG_MANAGER" == "dnf" ]]; then
    dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm
    dnf -qy module disable postgresql
    dnf install -y postgresql17
else
    yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-7-x86_64/pgdg-redhat-repo-latest.noarch.rpm
    yum install -y postgresql17
fi

# ── kubectl ───────────────────────────────────────────────────────────────────
echo "Installing kubectl..."
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg 2>/dev/null || true
if [[ "$PKG_MANAGER" == "apt" ]]; then
    apt-get install -y apt-transport-https gpg
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key \
        | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] \
https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /" \
        > /etc/apt/sources.list.d/kubernetes.list
    apt-get update -y
    apt-get install -y kubectl
else
    # Download the binary directly for non-apt systems
    KUBECTL_VERSION=$(curl -fsSL https://dl.k8s.io/release/stable.txt)
    curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
    chmod +x /usr/local/bin/kubectl
fi

# ── Azure CLI ─────────────────────────────────────────────────────────────────
echo "Installing Azure CLI..."
curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash

# ── Azure Functions Core Tools ────────────────────────────────────────────────
echo "Installing Azure Functions Core Tools..."
if [[ "$PKG_MANAGER" == "apt" ]]; then
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] \
https://packages.microsoft.com/repos/azure-functions focal main" \
        > /etc/apt/sources.list.d/azure-functions.list
    apt-get update -y
    apt-get install -y azure-functions-core-tools-4
else
    npm install -g azure-functions-core-tools@4 --unsafe-perm true
fi

# ── VS Code ───────────────────────────────────────────────────────────────────
echo "Installing VS Code..."
if [[ "$PKG_MANAGER" == "apt" ]]; then
    apt-get install -y wget gpg
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor > /etc/apt/keyrings/packages.microsoft.gpg
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/packages.microsoft.gpg] \
https://packages.microsoft.com/repos/code stable main" \
        > /etc/apt/sources.list.d/vscode.list
    apt-get update -y
    apt-get install -y code
elif [[ "$PKG_MANAGER" == "dnf" ]]; then
    rpm --import https://packages.microsoft.com/keys/microsoft.asc
    cat > /etc/yum.repos.d/vscode.repo <<'EOF'
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc
EOF
    dnf install -y code
else
    rpm --import https://packages.microsoft.com/keys/microsoft.asc
    cat > /etc/yum.repos.d/vscode.repo <<'EOF'
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc
EOF
    yum install -y code
fi

# ── VS Code extensions ────────────────────────────────────────────────────────
echo "Installing VS Code extensions..."
# Install extensions for the current user (run as the non-root user if possible)
if [[ -n "$SUDO_USER" ]]; then
    sudo -u "$SUDO_USER" code --install-extension ms-python.python
    sudo -u "$SUDO_USER" code --install-extension ms-azuretools.vscode-azurefunctions
else
    code --install-extension ms-python.python
    code --install-extension ms-azuretools.vscode-azurefunctions
fi

# ── pip upgrade ───────────────────────────────────────────────────────────────
echo "Upgrading pip..."
python3.12 -m pip install --upgrade pip

echo ""
echo "All tools installed successfully."
echo "Open a new terminal session to ensure all PATH updates take effect."
