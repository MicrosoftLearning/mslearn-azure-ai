# Install required tools using winget - run this script in an elevated PowerShell terminal

winget install -e --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements

winget install -e --id PostgreSQL.PostgreSQL.17 --source winget --accept-source-agreements --accept-package-agreements --override "--mode unattended --enable-components commandlinetools --disable-components server,pgAdmin,stackbuilder"

# Add PostgreSQL bin to system PATH if not already present
$pgPath = "C:\Program Files\PostgreSQL\17\bin"
if ($env:Path -notlike "*$pgPath*") {
    [Environment]::SetEnvironmentVariable("Path", $env:Path + ";$pgPath", "Machine")
    $env:Path += ";$pgPath"
}

winget install -e --id Kubernetes.kubectl --source winget --accept-source-agreements --accept-package-agreements

winget install -e --id Microsoft.AzureCLI --source winget --accept-source-agreements --accept-package-agreements

winget install -e --id Microsoft.Azure.FunctionsCoreTools --source winget --accept-source-agreements --accept-package-agreements

winget install -e --id Microsoft.VisualStudioCode --source winget --accept-source-agreements --accept-package-agreements


# Refresh the path environment variable for the current session to include the new tools without needing to restart the terminal
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

code --install-extension ms-python.python
code --install-extension ms-azuretools.vscode-azurefunctions
python -m pip install --upgrade pip
